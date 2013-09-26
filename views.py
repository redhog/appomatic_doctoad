import os.path
import threading
import subprocess
import django.shortcuts
import django.template.defaultfilters
import django.core.urlresolvers
import re
from django.conf import settings


class Repo(object):
    def __init__(self, root = None):
        self.root = root or os.path.join(settings.VIRTUALENV_DIR, "repo")
        self.lock = threading.Lock()

class RepoView(object):
    def __init__(self, repo, treeish = None):
        self.repo = repo
        self.treeish = treeish or 'master'

    def __enter__(self):
        self.repo.lock.acquire()
        subprocess.check_output(["git", "checkout", "-f", self.treeish], cwd=self.repo.root)
        return self

    def __exit__(self, type, value, traceback):
        self.repo.lock.release()
        return

    def ls_files(self):
        return [filename.rsplit(".", 1)[0]
                for filename
                in subprocess.check_output(["git", "ls-files"], cwd=self.repo.root).strip().split("\n")
                if filename.endswith(".md")]

    def cat_file(self, filename):
        filename = filename + ".md"
        filepath = os.path.join(self.repo.root, filename)
        if not os.path.exists(filepath):
            return 'Nothing here yet :)'
        with open(filepath) as f:
            return f.read()

    def branch(self, name, handle_duplicates = True):
        branch = name
        counter = 1
        while True:
            try:
                subprocess.check_output(["git", "branch", branch], cwd=self.repo.root)
                subprocess.check_output(["git", "checkout", branch], cwd=self.repo.root)
            except:
                if not handle_duplicates:
                    raise
                branch = "%s-%s" % (name, counter)
                counter += 1
            else:
                return branch

    def save(self, filename, content):
        filename = filename + ".md"
        with open(os.path.join(self.repo.root, filename), "w") as f:
            f.write(content.encode("utf-8"))
        subprocess.check_output(["git", "add", filename], cwd=self.repo.root)

    def commit(self, msg):
        subprocess.check_output(["git", "commit", "-m", msg], cwd=self.repo.root)
        
    def diff(self):
        output = subprocess.check_output(["git", "diff", "-p", "-U9999999", "--word-diff=plain", "master..." + self.treeish], cwd=self.repo.root)
        result = {}
        for file in output.split("diff --git ")[1:]:
            filename = file.split(" b/")[0][2:].rsplit(".", 1)[0]
            content = re.split(r"@@.*@@", file)[1]
            result[filename] = content
        return result

    def log(self):
        diffish = self.treeish
        if diffish != "master":
            diffish = "master.." + diffish

        output = subprocess.check_output(["git", "log", "-U4", "--word-diff=plain", diffish], cwd=self.repo.root)

        result = []
        ids = re.findall(r"commit ([0-9a-f]*)", output)
        datas = re.split(r"commit [0-9a-f]*\n", output)[1:]
        for id, commit in zip(ids, datas):
            author, date = re.findall(r"Author: (.*)\nDate: (.*)\n", commit)[0]
            comment = commit.split("\n\n", 1)[1].split("diff --git", 1)[0]
            resultcommit = {'id': id, 'files': {}, 'author': author.strip(), 'comment': comment.strip(), 'date': date.strip()}
            result.append(resultcommit)
            for file in commit.split("diff --git ")[1:]:
                filename = file.split(" b/")[0][2:].rsplit(".", 1)[0]
                content = re.split(r"@@.*@@", file)[1]
                resultcommit['files'][filename] = content
        return result


    def branches(self):
        closed = []
        open = []
        for branch in subprocess.check_output(["git", "branch"], cwd=self.repo.root).strip().split("\n"):
            branch = branch.strip(" *")
            if branch == "master": continue
            if branch.startswith("closed-"):
                closed.append(branch[len("closed-"):])
            else:
                open.append(branch)
        return {"open": open, "closed": closed}

    def current_branch(self):
        for branch in subprocess.check_output(["git", "branch"], cwd=self.repo.root).strip().split("\n"):
            branch = branch.strip()
            if branch.startswith("*"):
                return branch[1:].strip()

    def clashing_files(self, intotreeish = "master"):
        base = subprocess.check_output(["git", "merge-base", self.treeish, intotreeish], cwd=self.repo.root).strip()
        result = subprocess.check_output(["git", "merge-tree", base, self.treeish, intotreeish], cwd=self.repo.root).strip()
        return re.findall(r"changed in both\n *base *[0-9]* [0-9a-f]* (.*).md", result)

    def merge(self, fromtreeish):
        subprocess.check_output(["git", "merge", fromtreeish], cwd=self.repo.root)
        try:
            subprocess.check_output(["git", "branch", "-d", fromtreeish], cwd=self.repo.root)
        except:
            # If it's not a branch, just ignore...
            pass

    def update(self, fromtreeish = "master"):
        try:
            subprocess.check_output(["git", "merge", fromtreeish], cwd=self.repo.root)
            return True
        except:
            return False

    def close(self):
        subprocess.check_output(["git", "branch", "-m", self.treeish, "closed-" + self.treeish], cwd=self.repo.root)

repo = Repo()

def index(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/index.html", {'request': request, 'repo': view, 'view': 'index'})

def file(request):
    with RepoView(repo, request.GET.get("treeish", None) or "master") as view:
        if request.method == "POST":
            branch = view.branch(django.template.defaultfilters.slugify(request.POST["description"]))
            view.save(request.GET["file"], request.POST["source"])
            view.commit(request.POST["description"])
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + branch)
        return django.shortcuts.render(request, "appomatic_doctoad/file.html", {'request': request, 'repo': view, 'view': 'file'})

def change(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/change.html", {'request': request, 'repo': view, 'view': 'change'})

def log(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/log.html", {'request': request, 'repo': view, 'view': 'log'})

def merge(request):
    treeish = request.GET["treeish"]
    intotreeish = request.GET.get("intotreeish", "master")
    with RepoView(repo, intotreeish) as view:
        view.merge(treeish)
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index") + "?treeish=" + intotreeish)

def close(request):
    intotreeish = request.GET.get("intotreeish", "master")
    with RepoView(repo, request.GET["treeish"]) as view:
        view.close()
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index"))

def fix(request):
    with RepoView(repo, request.GET.get("treeish", None) or "master") as view:
        if request.method == "POST":
            view.close()
            branch = view.branch(django.template.defaultfilters.slugify(request.POST["description"]))
            view.update(request.GET.get("intotreeish", "master"))
            for name in request.POST.iterkeys():
                if name.endswith("_source"):
                    content = request.POST[name]
                    filename = request.POST[name.rsplit("_", 1)[0] + "_name"]
                    view.save(filename, content)
            view.commit(request.POST["description"])
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + branch)
        else:
            view.update(request.GET.get("intotreeish", "master"))
            return django.shortcuts.render(request, "appomatic_doctoad/fix.html", {'request': request, 'repo': view, 'view': 'fix'})
