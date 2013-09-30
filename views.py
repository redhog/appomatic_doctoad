import os.path
import threading
import subprocess
import django.shortcuts
import django.template.defaultfilters
import django.core.urlresolvers
import django.contrib.auth
import django.contrib.messages
import re
import django.contrib.auth.decorators
import tempfile
from django.conf import settings

class Repo(object):
    def __init__(self, root = None):
        self.root = root or os.path.join(settings.VIRTUALENV_DIR, "repo")
        self.lock = threading.Lock()

class CommandError(subprocess.CalledProcessError):
    def __init__(self, stderr, base):
        subprocess.CalledProcessError.__init__(self, base.returncode, base.cmd, base.output)
        self.stderr = stderr
    def __str__(self):
        return "%s:\n%s\n%s" % (self.cmd, self.output, self.stderr)

def get_parent(treeish):
    if '--' in treeish:
        parent = treeish.rsplit('--', 1)[0]
        if parent != 'closed':
            return parent
    return "master"

class RepoView(object):
    def __init__(self, repo, request, treeish = None):
        self.repo = repo
        self.request = request
        self.treeish = treeish or 'master'

    def run(self, *arg):
        os.ftruncate(self.stderr, 0)
        try:
            return subprocess.check_output([a.encode("utf-8") for a in arg], cwd=self.repo.root, stderr=self.stderr).decode("utf-8")
        except subprocess.CalledProcessError, e:
            with os.fdopen(os.dup(self.stderr), "r") as f:
                f.seek(0)
                raise CommandError(f.read(), e)

    def __enter__(self):
        self.stderr, self.stderrpath = tempfile.mkstemp()
        self.repo.lock.acquire()
        try:
            name = email = ""
            if self.request.user.is_authenticated():
                name, email = self.request.user.get_full_name(), self.request.user.email
            elif 'doctoad_name' in self.request.session:
                name, email = self.request.session["doctoad_name"], self.request.session["doctoad_email"]
            if not name.strip(): name = "Anonymous"
            if not email.strip(): email = "anonymous@inter.net"

            self.run("git", "config", "--replace-all", "user.name", name)
            self.run("git", "config", "--replace-all", "user.email", email)

            self.run("git", "checkout", "-f", self.treeish)
        except:
            self.repo.lock.release()
            raise
        return self

    def __exit__(self, type, value, traceback):
        self.repo.lock.release()
        os.unlink(self.stderrpath)
        return

    def ls_files(self):
        return [filename.rsplit(".", 1)[0]
                for filename
                in self.run("git", "ls-files").strip().split("\n")
                if filename.endswith(".md")]

    def cat_file(self, filename):
        filename = filename + ".md"
        filepath = os.path.join(self.repo.root, filename)
        if not os.path.exists(filepath):
            return 'Nothing here yet :)'
        with open(filepath) as f:
            return f.read()

    def is_new_file(self, filename):
        filename = filename + ".md"
        filepath = os.path.join(self.repo.root, filename)
        return not os.path.exists(filepath)

    def save(self, filename, content):
        filename = filename + ".md"
        with open(os.path.join(self.repo.root, filename), "w") as f:
            f.write(content.encode("utf-8"))
        self.run("git", "add", filename)

    def commit(self, msg):
        self.run("git", "commit", "-m", msg)
        
    def diff(self):
        output = self.run("git", "diff", "-p", "-U9999999", "--word-diff=plain", "master..." + self.treeish)
        if not output.strip():
            output = self.run("git", "diff", "-p", "-U9999999", "--word-diff=plain", self.treeish + "^..." + self.treeish)
            
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

        output = self.run("git", "log", "-U4", "--word-diff=plain", diffish)
        if not output.strip():
            output = self.run("git", "log", "-U4", "--word-diff=plain", self.treeish + "^..." + self.treeish)

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

    def branch(self, name, handle_duplicates = True):
        if self.treeish != "master":
            name = self.treeish + "--" + name
        branch = name
        counter = 1
        while True:
            try:
                self.run("git", "branch", branch)
                self.run("git", "checkout", branch)
            except:
                if not handle_duplicates:
                    raise
                branch = "%s-%s" % (name, counter)
                counter += 1
            else:
                return branch

    def branches(self):
        branches = {}
        for branch in self.run("git", "branch", "-v").strip().split("\n"):
            branch = branch.strip(" *")
            if branch == "master": continue
            branch, commit, description = re.split(r"  *", branch, 2)
            branch = branch.split("--")
            node = branches
            for i in xrange(0, len(branch)):
                if branch[i] not in node:
                    node[branch[i]] = {"treeish": '--'.join(branch[:i + 1]), 'children': {}, 'description': branch[i]}
                node = node[branch[i]]
                if i == len(branch) - 1:
                    node['description'] = description
                node = node['children']
        if self.treeish != "master":
            for item in self.treeish.split("--"):
                if item not in branches:
                    return []
                branches = branches[item]['children']
        def mangle(node):
            res = node.values()
            for item in res:
                item['children'] = mangle(item['children'])
            res.sort(lambda x, y: cmp(x['description'], y['description']))
            return res
        return mangle(branches)

    def current_branch(self):
        for branch in self.run("git", "branch", "-v").strip().split("\n"):
            branch = branch.strip()
            if branch.startswith("*"):
                branch, description = re.match("^\* (.*[^ ])  *[0-9a-f]{7} (.*)$", branch).groups()
                return branch, description

    def clashing_files(self, intotreeish = None):
        if not intotreeish:
            intotreeish = get_parent(self.treeish)
        base = self.run("git", "merge-base", self.treeish, intotreeish).strip()
        result = self.run("git", "merge-tree", base, self.treeish, intotreeish).strip()
        return re.findall(r"changed in both\n *base *[0-9]* [0-9a-f]* (.*).md", result)

    def merge(self, fromtreeish):
        self.run("git", "merge", fromtreeish)
        try:
            self.run("git", "branch", "-d", fromtreeish)
        except:
            # If it's not a branch, just ignore...
            pass

    def update(self, fromtreeish = "master"):
        try:
            self.run("git", "merge", fromtreeish)
            return True
        except:
            return False

    def close(self):
        self.run("git", "branch", "-m", self.treeish, "closed--" + self.treeish)

repo = Repo()

def landing(request):
    if request.method == "POST":
        if 'action-use' in request.POST:
            request.session["doctoad_name"] = request.POST["name"]
            request.session["doctoad_email"] = request.POST["email"]
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index"))
        elif 'action-login' in request.POST:
            user = django.contrib.auth.authenticate(username=request.POST['username'], password=request.POST['password'])
            if user is not None and user.is_active:
                django.contrib.auth.login(request, user)
                return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index"))
            django.contrib.messages.error(request, 'Bad username or password.')
    return django.shortcuts.render(request, "appomatic_doctoad/landing.html", {'request': request, 'view': 'landing'})

def index(request):
    with RepoView(repo, request, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/index.html", {'request': request, 'repo': view, 'view': 'index'})

def file(request):
    with RepoView(repo, request, request.GET.get("treeish", None) or "master") as view:
        if request.method == "POST":
            branch = view.branch(django.template.defaultfilters.slugify(request.POST["description"]))
            view.save(request.GET["file"], request.POST["source"])
            view.commit(request.POST["description"])
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + branch)
        return django.shortcuts.render(request, "appomatic_doctoad/file.html", {'request': request, 'repo': view, 'view': 'file'})

def change(request):
    with RepoView(repo, request, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/change.html", {'request': request, 'repo': view, 'view': 'change'})

def log(request):
    with RepoView(repo, request, request.GET.get("treeish", "master")) as view:
        return django.shortcuts.render(request, "appomatic_doctoad/log.html", {'request': request, 'repo': view, 'view': 'log'})

@django.contrib.auth.decorators.permission_required('appomatic_doctoad.merge')
def merge(request):
    treeish = request.GET.get("treeish", None) or "master"
    intotreeish = request.GET.get("intotreeish", get_parent(treeish))
    with RepoView(repo, request, intotreeish) as view:
        view.merge(treeish)
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index") + "?treeish=" + intotreeish)

@django.contrib.auth.decorators.permission_required('appomatic_doctoad.close')
def close(request):
    with RepoView(repo, request, request.GET["treeish"]) as view:
        view.close()
        return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.index"))

def fix(request):
    treeish = request.GET.get("treeish", None) or "master"
    with RepoView(repo, request, treeish) as view:
        if request.method == "POST":
            view.close()
            branch = view.branch(django.template.defaultfilters.slugify(request.POST["description"]))
            view.update(request.GET.get("intotreeish", get_parent(treeish)))
            for name in request.POST.iterkeys():
                if name.endswith("_source"):
                    content = request.POST[name]
                    filename = request.POST[name.rsplit("_", 1)[0] + "_name"]
                    view.save(filename, content)
            view.commit(request.POST["description"])
            return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.change") + "?treeish=" + branch)
        else:
            view.update(request.GET.get("intotreeish", get_parent(treeish)))
            return django.shortcuts.render(request, "appomatic_doctoad/fix.html", {'request': request, 'repo': view, 'view': 'fix'})

def logout(request):
    django.contrib.auth.logout(request)
    return django.shortcuts.redirect(django.core.urlresolvers.reverse("appomatic_doctoad.views.landing"))
