"""P22:git 钩子和钩子管理器的兼容(每条都在临时仓库里真跑 git;钩子只装在临时仓库里,绝不装到别处)。
husky 没有联网安装,用它 v9 写出的启动脚本的等价物(.husky/_/h、.husky/_/<钩子名>)模拟;pre-commit 框架要有 pre_commit 包(没有就跳过这一条,打印原因)。
测:① husky ② pre-commit 框架 ③ 相对 hooksPath 的第二个 worktree ④ 全局 hooksPath 下 uninstall ⑤ autocrlf=true 的克隆 ⑥ inbox 合并 ⑦ 链接大小写。
全过打印 OK,否则列出失败项并退出码 1。不含计时断言。"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

from helpers import NOMESS, PLUGIN, expect, fails, put

GUARD = os.path.join(PLUGIN, "hooks", "guard.py")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
BAD = "x = 'FORBIDDEN'\n"
CFG = {"format": "nomess/1", "main_branch": "main", "lang": "en",
       "check": {"rules": [{"id": "R1", "level": "red", "what": "no FORBIDDEN", "why": "test", "glob": "src/**", "forbid": "FORBIDDEN"}]}}
HUSKY_H = '''#!/usr/bin/env sh
n=$(basename "$0")
s=$(dirname "$(dirname "$0")")/$n
[ ! -f "$s" ] && exit 0
sh -e "$s" "$@"
c=$?
[ $c != 0 ] && echo "husky - $n script failed (code $c)"
exit $c
'''
HUSKY_HOOK = '#!/usr/bin/env sh\n. "$(dirname "$0")/h"\n'


def git(cwd, *a, env=None, check=True):
    p = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV)
    if check and p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p


def nomess(cwd, *a, env=None):
    return subprocess.run([sys.executable, NOMESS, *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV)


def mk(tmp, name, files=(), cfg=None):
    root = os.path.join(tmp, name)
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("core.autocrlf", "false")):
        git(root, "config", k, v)
    put(root, "nomess.json", json.dumps(dict(CFG, **(cfg or {}))))
    put(root, "src/a.py", "# a\nx = 1\n")
    for rel, text in files:
        put(root, rel, text)
    return root


def commit(root, msg="t", env=None):
    return git(root, "commit", "-qm", msg, env=env, check=False)


def husky_layout(root, user_pre, user_merge):
    put(root, ".husky/_/h", HUSKY_H)
    for h in ("pre-commit", "pre-merge-commit"):
        put(root, ".husky/_/" + h, HUSKY_HOOK)
    put(root, ".husky/pre-commit", user_pre)
    put(root, ".husky/pre-merge-commit", user_merge)
    git(root, "config", "core.hooksPath", ".husky/_")


def t_husky(tmp):
    recipe = lambda stage: 'h="$(git rev-parse --git-common-dir)/nomess-hook"\nif [ -f "$h" ]; then sh "$h" %s || exit $?; fi\n' % stage
    # 配方在中间、后面还有命令(husky 用 sh -e 跑用户脚本,退出码要原样传出)
    root = mk(tmp, "husky")
    husky_layout(root, "echo before\n" + recipe("pre-commit") + "echo after\n", recipe("pre-merge-commit"))
    p = nomess(root, "hooks", "install")
    expect(p.returncode == 0 and "installed" not in p.stdout, "① husky:install 不该往 .husky/_ 写钩子: " + p.stdout)
    expect(not os.path.exists(os.path.join(root, ".husky", "_", "nomess")), "① husky:不该在 .husky/_ 里留东西")
    st = json.loads(subprocess.run([sys.executable, "-c", "import sys,json; sys.path.insert(0,%r); import githook; print(json.dumps(githook.status(%r)))"
                                    % (os.path.join(PLUGIN, "scripts"), root)], capture_output=True, text=True, env=ENV).stdout)
    expect(st["manager"] == "husky" and set(st["hooks"].values()) == {"wired"}, "① husky:用户脚本里有配方应算接入: %r" % st)
    git(root, "add", "-A")
    expect(commit(root, "init").returncode == 0, "① husky:干净提交应过")
    git(root, "checkout", "-qb", "feat")
    put(root, "src/bad.py", BAD)
    git(root, "add", "src/bad.py")
    p = commit(root)
    expect(p.returncode != 0 and "R1" in p.stderr, "① husky:pre-commit 阶段红项应挡(配方不在末行): " + p.stderr)
    git(root, "commit", "-qnm", "bad", check=False)  # 人走放宽流程:带违规进分支
    git(root, "checkout", "-q", "main")
    p = git(root, "merge", "--no-ff", "-m", "m", "feat", check=False)
    expect(p.returncode != 0 and "R1" in p.stderr, "① husky:pre-merge-commit 阶段红项应挡: " + p.stderr)
    git(root, "merge", "--abort", check=False)
    # 没装 nomess 的克隆:配方里 [ -f "$h" ] 为假,返回 0,提交成功
    clone = os.path.join(tmp, "husky-clone")
    git(tmp, "clone", "-q", root, clone)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(clone, "config", k, v)
    husky_layout(clone, "echo before\n" + recipe("pre-commit") + "echo after\n", recipe("pre-merge-commit"))
    git(clone, "checkout", "-qb", "work")
    put(clone, "src/bad.py", BAD)
    git(clone, "add", "src/bad.py")
    expect(commit(clone).returncode == 0, "① husky:没装 nomess 的克隆提交应成功")


def t_framework(tmp):
    spec = importlib.util.find_spec("pre_commit")
    if spec is None:
        print("   跳过 ②:没有 pre_commit 包")
        return
    env = dict(ENV, PYTHONPATH=os.pathsep.join(filter(None, [os.path.dirname(os.path.dirname(spec.origin)), ENV.get("PYTHONPATH")])),
               PRE_COMMIT_HOME=os.path.join(tmp, "pc-home"))
    root = mk(tmp, "framework")
    git(root, "add", "-A")
    expect(commit(root, "init", env=env).returncode == 0, "② 框架:初始提交")
    pc = lambda *a: subprocess.run([sys.executable, "-m", "pre_commit", *a], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    expect(pc("install", "--hook-type", "pre-commit", "--hook-type", "pre-merge-commit").returncode == 0, "② 框架:pre-commit install")
    put(root, ".pre-commit-config.yaml", "repos: []\n")
    p = nomess(root, "hooks", "install", env=env)
    lines = p.stdout.splitlines()
    i = next((n for n, l in enumerate(lines) if l.startswith("- repo: local")), None)
    expect(i is not None and "pre-commit install --hook-type pre-commit --hook-type pre-merge-commit" in p.stdout, "② 框架:install 应打出框架配方: " + p.stdout)
    if i is None:
        return
    j = next(n for n, l in enumerate(lines) if l.startswith("pre-commit install"))
    put(root, ".pre-commit-config.yaml", "repos:\n" + "\n".join(lines[i:j]) + "\n")
    git(root, "add", ".pre-commit-config.yaml")
    p = commit(root, "config", env=env)  # 主分支上:nomess 刷新出系统图,框架不该报"文件被改"
    expect(p.returncode == 0 and "files were modified" not in p.stdout + p.stderr, "② 框架:主分支刷新后提交应成功、框架不报文件被改: %r %r" % (p.stdout, p.stderr))
    expect("docs/system-map/index.md" in git(root, "show", "--name-only", "--format=", "HEAD").stdout, "② 框架:刷新的系统图应在这次提交里")
    st = json.loads(subprocess.run([sys.executable, "-c", "import sys,json; sys.path.insert(0,%r); import githook; print(json.dumps(githook.status(%r)))"
                                    % (os.path.join(PLUGIN, "scripts"), root)], capture_output=True, text=True, env=env).stdout)
    expect(st["manager"] == "framework" and set(st["hooks"].values()) == {"wired"}, "② 框架:配置里有两个 id 应算接入: %r" % st)
    git(root, "checkout", "-qb", "feat")
    put(root, "src/bad.py", BAD)
    git(root, "add", "src/bad.py")
    p = commit(root, env=env)
    expect(p.returncode != 0 and "R1" in p.stdout + p.stderr, "② 框架:pre-commit 阶段红项应挡: %r %r" % (p.stdout, p.stderr))
    git(root, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "bad", env=env, check=False)
    git(root, "checkout", "-q", "main")
    p = git(root, "merge", "--no-ff", "-m", "m", "feat", env=env, check=False)
    expect(p.returncode != 0 and "R1" in p.stdout + p.stderr, "② 框架:pre-merge-commit 阶段红项应挡: %r %r" % (p.stdout, p.stderr))


def t_worktree(tmp):
    root = mk(tmp, "wt1")
    git(root, "config", "core.hooksPath", ".hooks")
    put(root, ".git/info/exclude", ".hooks/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    expect(nomess(root, "hooks", "install").returncode == 0, "③ install")
    wt2 = os.path.join(tmp, "wt2")
    git(root, "worktree", "add", "-q", "-b", "other", wt2)
    out = nomess(root, "doctor").stdout
    bad = [l for l in out.splitlines() if "not wired" in l]
    expect(len(bad) == 1 and os.path.realpath(wt2).replace("\\", "/") in bad[0], "③ 相对 hooksPath:doctor 应单独报第二个 worktree 没接入: %r" % out)
    expect("git hooks wired" in out, "③ 相对 hooksPath:第一个 worktree 接了应报接入: %r" % out)


def t_global_uninstall(tmp):
    root = mk(tmp, "glob")
    shared = os.path.join(tmp, "shared-hooks")
    put(shared, "commit-msg", "#!/bin/sh\nexit 0\n")
    put(shared, "post-checkout", "#!/bin/sh\nexit 0\n")
    git(root, "config", "core.hooksPath", shared.replace("\\", "/"))
    expect(nomess(root, "hooks", "install").returncode == 0, "④ install")
    ours = [h for h in ("pre-commit", "pre-merge-commit") if os.path.exists(os.path.join(shared, h))]
    expect(ours == ["pre-commit", "pre-merge-commit"], "④ install 应写两个钩子: %r" % ours)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    expect(nomess(root, "hooks", "uninstall").returncode == 0, "④ uninstall")
    left = sorted(os.listdir(shared))
    expect(left == ["commit-msg", "post-checkout"], "④ uninstall 只删自己写的文件: %r" % left)
    launcher = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True).stdout.strip()
    body = open(os.path.join(root, launcher, "nomess-hook"), encoding="utf-8").read()
    expect(body.rstrip().endswith("exit 0") and "exec" not in body, "④ uninstall 后启动器应是存根: " + body)
    hook_in = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": root})
    g = subprocess.run([sys.executable, GUARD], input=hook_in, capture_output=True, text=True, env=ENV)
    expect(g.returncode == 0 and g.stdout.strip() == "", "④ 存根时 guard 不 deny 也不提示: " + g.stdout)
    expect("switched off" in nomess(root, "doctor").stdout, "④ 存根时 doctor 报已停用")
    nomess(root, "hooks", "install")
    g = subprocess.run([sys.executable, GUARD], input=hook_in, capture_output=True, text=True, env=ENV)
    expect(g.stdout.strip() == "" and "exec" in open(os.path.join(root, launcher, "nomess-hook"), encoding="utf-8").read(), "④ install 恢复")


def t_autocrlf(tmp):
    attrs = "docs/system-map/** text eol=lf\n.claude/rules/nomess/** text eol=lf\n"
    lesson = "# Lessons\n\n## Mind the save format\nWhen: src/**\nStatus: verified\nPaths: src/**\nRule: keep the save format\nWhat: x\n"
    root = mk(tmp, "crlf-src", [(".gitattributes", attrs), ("docs/lessons/core.md", lesson),
                                ("docs/design.md", "# Design\n\n<!-- GEN:entry BEGIN -->\n<!-- GEN:entry END -->\n")],
              {"docgen": {"entry": {"file": "docs/design.md", "builtin": "agents-entry"}}})
    expect(nomess(root, "refresh").returncode == 0, "⑤ refresh")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    clone = os.path.join(tmp, "crlf-clone")
    git(tmp, "clone", "-q", "-c", "core.autocrlf=true", root, clone)
    design = open(os.path.join(clone, "docs", "design.md"), "rb").read()
    expect(b"\r\n" in design, "⑤ 前提:克隆里手写文件应是 CRLF")
    for cmd in (("docgen", "--check"), ("map", "--check"), ("rules", "--check")):
        p = nomess(clone, *cmd)
        expect(p.returncode == 0, "⑤ autocrlf=true 的克隆 %s 不该报过时: %r" % (" ".join(cmd), p.stdout))
    out = nomess(clone, "check", "--all").stdout
    expect("GEN" not in out and "RUL2" not in out, "⑤ check 不该报生成物过时: " + out)
    rule = next(f for f in os.listdir(os.path.join(clone, ".claude", "rules", "nomess")))
    attr = git(clone, "check-attr", "eol", "--", "docs/system-map/index.md", ".claude/rules/nomess/" + rule).stdout.splitlines()
    expect(len(attr) == 2 and all(l.endswith(": lf") for l in attr), "⑤ 两个生成目录下的文件 eol 都应是 lf: %r" % attr)


def t_inbox_merge(tmp):
    root = mk(tmp, "inbox", [(".gitattributes", "docs/lessons/inbox.md merge=union\n"), ("docs/lessons/inbox.md", "# inbox (to be sorted, append only)\n")])
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    for branch, title in (("a", "Alpha entry"), ("b", "Beta entry")):
        git(root, "checkout", "-q", "-b", branch, "main")
        expect(nomess(root, "lessons", "add", title, "-s", "s", "-b", "body").returncode == 0, "⑥ lessons add")
        git(root, "add", "-A")
        git(root, "commit", "-qm", branch)
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-edit", "a")
    p = git(root, "merge", "--no-edit", "b", check=False)
    text = open(os.path.join(root, "docs", "lessons", "inbox.md"), encoding="utf-8").read()
    expect(p.returncode == 0 and "Alpha entry" in text and "Beta entry" in text, "⑥ 两个分支各加一条,合并不冲突、两条都在: %r %r" % (p.stderr, text))
    expect("L5" not in nomess(root, "check", "--all").stdout, "⑥ 合并出的 inbox 结构应干净")


def t_link_case(tmp):
    root = mk(tmp, "case", [("docs/Readme.md", "# r\n"), ("docs/index.md", "see [x](readme.md) and [y](Readme.md)\n")])
    p = nomess(root, "check", "--all")
    expect("DOC1 docs/index.md:1" in p.stdout and p.stdout.count("DOC1") == 1 and p.returncode == 1,
           "⑦ 大小写写错的链接应报红,写对的不报(在 Windows 上也一样): %r" % p.stdout)


def main():
    tmp = tempfile.mkdtemp(prefix="nm-compat-")
    try:
        for fn in (t_husky, t_framework, t_worktree, t_global_uninstall, t_autocrlf, t_inbox_merge, t_link_case):
            print("== " + fn.__name__)
            fn(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("FAIL %d:" % len(fails))
        for f in fails:
            print(" - " + f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
