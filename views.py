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
        return subprocess.check_output(["git", "ls-files"], cwd=self.repo.root).strip().split("\n")

    def cat_file(self, filename):
        filepath = os.path.join(self.repo.root, filename)
        if not os.path.exists(filepath):
            return 'Nothing here yet :)'
        with open(filepath) as f:
            return f.read()

    def branch(self, name):
        subprocess.check_output(["git", "branch", name], cwd=self.repo.root)
        subprocess.check_output(["git", "checkout", name], cwd=self.repo.root)

    def save(self, filename, content):
        with open(os.path.join(self.repo.root, filename), "w") as f:
            f.write(content.encode("utf-8"))
        subprocess.check_output(["git", "add", filename], cwd=self.repo.root)

    def commit(self, msg):
        subprocess.check_output(["git", "commit", "-m", msg], cwd=self.repo.root)
        
    def diff(self):
        output = subprocess.check_output(["git", "diff", "-p", "-U9999999", "--word-diff=plain", "master.." + self.treeish], cwd=self.repo.root)
        result = {}
        for file in output.split("diff --git ")[1:]:
            filename = file.split(" b/")[0][2:]
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
                filename = file.split(" b/")[0][2:]
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

    def mergeable(self, intotreeish = "master"):
        base = subprocess.check_output(["git", "merge-base", self.treeish, intotreeish], cwd=self.repo.root).strip()
        result = subprocess.check_output(["git", "merge-tree", base, self.treeish, intotreeish], cwd=self.repo.root).strip()
        return '<<<<<<<' not in result

    def merge(self, fromtreeish):
        subprocess.check_output(["git", "merge", fromtreeish], cwd=self.repo.root)
        try:
            subprocess.check_output(["git", "branch", "-d", fromtreeish], cwd=self.repo.root)
        except:
            # If it's not a branch, just ignore...
            pass

    def fix(self, intotreeish = "master"):
        current = self.current_branch()
        fixed = current + "-fix"
        subprocess.check_output(["git", "branch", fixed], cwd=self.repo.root)
        subprocess.check_output(["git", "checkout", fixed], cwd=self.repo.root)
        try:
            subprocess.check_output(["git", "merge", intotreeish], cwd=self.repo.root)
        except:
            # Yes, this will fail... of course it will fail
            pass
        subprocess.check_output(["git", "add", "."], cwd=self.repo.root)
        subprocess.check_output(["git", "commit", "-m", "Merging master to allow fix"], cwd=self.repo.root)
        subprocess.check_output(["git", "branch", "-m", current, "closed-" + current], cwd=self.repo.root)
        return fixed

repo = Repo()

def index(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/index.html", {'request': request, 'repo': view})

def file(request):
    with RepoView(repo, request.GET.get("treeish", None) or "master") as view:
        if request.method == "POST":
            base = branch = django.template.defaultfilters.slugify(request.POST["description"])
            counter = 1
            while True:
                try:
                    view.branch(branch)
                except:
                    branch = "%s-%s" % (base, counter)
                    counter += 1
                else:
                    break
            view.save(request.GET["file"], request.POST["source"])
            view.commit(request.POST["description"])
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + branch)
        return django.shortcuts.render(request, "appomatic_doctoad/file.html", {'request': request, 'repo': view})

def change(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/change.html", {'request': request, 'repo': view})

def log(request):
    with RepoView(repo, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/log.html", {'request': request, 'repo': view})

def merge(request):
    treeish = request.GET["treeish"]
    intotreeish = request.GET.get("intotreeish", "master")
    with RepoView(repo, intotreeish) as view:
        view.merge(treeish)
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index") + "?treeish=" + intotreeish)

def fix(request):
    treeish = request.GET["treeish"]
    intotreeish = request.GET.get("intotreeish", "master")
    with RepoView(repo, treeish) as view:
        fixed = view.fix(intotreeish)
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + fixed)
