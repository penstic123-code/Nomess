"""P20 的 git 钩子测试:每条都在临时仓库里真跑 git(钩子装在临时仓库里,绝不装到别处),只测 git 的边界行为和快照 / 原子写。
读代码就能确认的验收(某脚本改成经快照读、报错改英文、Python 版本不够退出 2)不写测试,见交回。
全过打印 OK,否则列出失败项并退出码 1。不含计时断言。"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.normpath(os.path.join(HERE, ".."))
SCRIPTS = os.path.join(PLUGIN, "scripts")
GUARD = os.path.join(PLUGIN, "hooks", "guard.py")
sys.path.insert(0, SCRIPTS)
import nm_config  # noqa: E402

fails = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
BAD = "x = 'FORBIDDEN'\n"
CFG = {"format": "nomess/1", "main_branch": "main", "lang": "en", "size": "medium",
       "check": {"rules": [{"id": "R1", "level": "red", "what": "no FORBIDDEN", "why": "test", "glob": "src/**", "forbid": "FORBIDDEN"}]}}


def expect(cond, what):
    if not cond:
        fails.append(what)
        print("   FAIL: " + what)


def git(cwd, *a, check=True):
    p = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    if check and p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p


def w(root, rel, text, mode="w"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, encoding=None if "b" in mode else "utf-8", newline=None if "b" in mode else "\n") as f:
        f.write(text)


def r(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", newline="") as f:
        return f.read()


def nomess(cwd, *a, script=None):
    return subprocess.run([sys.executable, script or os.path.join(SCRIPTS, "nomess.py"), *a], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV)


def mk(tmp, name, cfg=None, files=(), hooks=True, first_commit=True):
    """临时仓库:主分支 main,装好钩子,第一次提交(主分支上会刷新出系统图)。"""
    root = os.path.join(tmp, name)
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("core.autocrlf", "false")):
        git(root, "config", k, v)
    w(root, "nomess.json", json.dumps(dict(CFG, **(cfg or {}))))
    w(root, ".gitignore", ".nomess/\n")
    w(root, "src/a.py", "# a\nx = 1\n")
    for rel, text in files:
        w(root, rel, text)
    if hooks:
        expect(nomess(root, "hooks", "install").returncode == 0, "hooks install")
    if first_commit:
        git(root, "add", "-A")
        p = git(root, "commit", "-qm", "init", check=False)
        expect(p.returncode == 0, "初始提交应过: " + p.stderr)
    return root


def commit(root, *a):
    return git(root, "commit", "-q", *a, "-m", "t", check=False)


def head_files(root, rev="HEAD"):
    return git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", rev).stdout.split()


def clean(root):
    return git(root, "status", "--porcelain").stdout.strip() == ""


def digests(root):
    out = {}
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in (".git", ".nomess")]  # .nomess 是本机缓存(已忽略),检查会写
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = hashlib.md5(open(p, "rb").read()).hexdigest()
    return out, git(root, "ls-files", "-s").stdout


def t_gate_basic(tmp):
    root = mk(tmp, "basic")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/bad.py", BAD)
    git(root, "add", "src/bad.py")
    expect(commit(root).returncode != 0, "① 暂存的违规文件应被挡")
    # 暂存的是干净内容,工作区(同一文件)有未暂存的违规草稿(git add -p 剩下的部分同理)
    w(root, "src/a.py", "# a\nx = 2\n")
    git(root, "add", "src/a.py")
    git(root, "reset", "-q", "src/bad.py")
    os.remove(os.path.join(root, "src", "bad.py"))
    w(root, "src/a.py", "# a\nx = 2\n" + BAD)
    expect(commit(root).returncode == 0, "① 暂存干净、工作区有违规草稿时应通过")
    expect("FORBIDDEN" not in git(root, "show", "HEAD:src/a.py").stdout, "① 提交的是暂存内容")


def t_gate_staged_config(tmp):
    root = mk(tmp, "cfg")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/b.py", BAD)
    git(root, "add", "src/b.py")
    cfg = json.loads(r(root, "nomess.json"))
    cfg["check"]["rules"] = []
    w(root, "nomess.json", json.dumps(cfg))  # 工作区的新配置没有规则,没暂存
    expect(commit(root).returncode != 0, "① 暂存的旧配置有规则、工作区新配置没有:按暂存的判,应挡")


def t_gate_delete_config(tmp):
    root = mk(tmp, "delcfg")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/b.py", BAD)
    git(root, "add", "src/b.py")
    git(root, "rm", "-q", "nomess.json")
    p = commit(root)
    expect(p.returncode != 0 and "nomess.json" in p.stderr, "① 提交里删 nomess.json 并带违规应被挡: " + p.stderr)


def t_first_commit(tmp):
    root = mk(tmp, "first", files=[("src/bad.py", BAD)], first_commit=False)
    git(root, "add", "-A")
    expect(commit(root).returncode != 0, "⑤ 首次提交(没有 HEAD)带违规应被挡")
    os.remove(os.path.join(root, "src", "bad.py"))
    git(root, "add", "-A")
    expect(commit(root).returncode == 0, "⑤ 首次提交干净应通过")


def t_refresh_plain(tmp):
    root = mk(tmp, "plain")
    expect("docs/system-map/index.md" in head_files(root), "② 初始提交里应含生成的系统图")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    expect(commit(root).returncode == 0 and clean(root), "② 主分支普通提交后应干净")
    expect("docs/system-map/files.md" in head_files(root) and "src/n.py" in r(root, "docs/system-map/files.md"), "② 生成物应在同一提交里")


def t_refresh_all(tmp):
    root = mk(tmp, "all")
    w(root, "src/a.py", "# a\nx = 9\n")
    p = git(root, "commit", "-aqm", "t", check=False)
    expect(p.returncode == 0 and clean(root), "② commit -a 后应干净: " + p.stderr + git(root, "status", "--porcelain").stdout)


def t_refresh_include(tmp):
    root = mk(tmp, "include")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    w(root, "src/a.py", "# a\nx = 3\n")
    p = commit(root, "--include", "src/a.py")
    expect(p.returncode == 0 and clean(root), "② commit --include 后应干净: " + p.stderr)


def t_path_commit_checked_not_refreshed(tmp):
    root = mk(tmp, "path")
    w(root, "src/bad.py", BAD)
    git(root, "add", "-N", "src/bad.py")
    expect(commit(root, "src/bad.py").returncode != 0, "② 带路径提交应照查")
    os.remove(os.path.join(root, "src", "bad.py"))
    git(root, "reset", "-q")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    expect(commit(root, "src/n.py").returncode == 0, "② 带路径提交干净应通过")
    expect("docs/system-map/files.md" not in head_files(root), "② 带路径提交不刷新")


def t_amend_only_message(tmp):
    root = mk(tmp, "amend")
    w(root, "docs/system-map/files.md", "stale\n")
    git(root, "add", "docs/system-map/files.md")
    git(root, "commit", "-qm", "stale map", "--no-verify")
    tree = git(root, "rev-parse", "HEAD^{tree}").stdout
    p = git(root, "commit", "-q", "--amend", "-m", "new message", check=False)
    expect(p.returncode == 0 and git(root, "rev-parse", "HEAD^{tree}").stdout == tree, "② 只改信息的 amend 不带进文件改动")


def t_amend_only_path(tmp):
    root = mk(tmp, "amendonly")
    w(root, "src/bad.py", BAD)
    git(root, "add", "-N", "src/bad.py")
    expect(commit(root, "--only", "--amend", "src/bad.py").returncode != 0, "② --only --amend 带违规应被挡")


def t_feature_no_refresh(tmp):
    root = mk(tmp, "feat")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    expect(commit(root).returncode == 0 and head_files(root) == ["src/n.py"], "② 功能分支不刷新: %r" % head_files(root))


def t_candidate_tree_old_link(tmp):
    root = mk(tmp, "cand", files=[("src/x.py", "# x\n")])
    w(root, "docs/system-map/files.md", "old [x](../../src/x.py)\n")
    git(root, "add", "docs/system-map/files.md")
    git(root, "commit", "-qm", "old link", "--no-verify")
    git(root, "branch", "feat")
    git(root, "rm", "-q", "src/x.py")
    p = commit(root)
    expect(p.returncode == 0 and "src/x.py" not in r(root, "docs/system-map/files.md"), "②b 主分支:删源文件、旧系统图链接它,刷新后应过: " + p.stderr)
    git(root, "checkout", "-q", "feat")
    git(root, "rm", "-q", "src/x.py")
    expect(commit(root).returncode != 0, "②b 功能分支不刷新,同样的提交应被断链挡住")


def t_broken_rule_frontmatter(tmp):
    root = mk(tmp, "fm")
    git(root, "checkout", "-qb", "feat")
    w(root, ".claude/rules/nomess/abcd1234.md", "no frontmatter\n")
    git(root, "add", "-A")
    p = commit(root)
    expect(p.returncode != 0 and "RUL1" in p.stderr, "②b 规则文件 frontmatter 坏应被挡: " + p.stderr)


LESSON = "# L\n\n## Pitfall\nWhen: editing src\nStatus: verified\nPaths: src/**/*.py\nRule: keep it small\nWhat: because\n"


def t_stale_rule_file_removed(tmp):
    root = mk(tmp, "rulegone", files=[("docs/lessons/core.md", LESSON)])
    expect(any(f.startswith(".claude/rules/nomess/") for f in head_files(root)), "②b 前提:教训生成了规则文件")
    git(root, "rm", "-q", "docs/lessons/core.md")
    expect(commit(root).returncode == 0, "②b 删教训的提交应过")
    expect(git(root, "ls-files", ".claude/rules/nomess").stdout.strip() == "" and clean(root), "②b 旧规则文件应在同一提交里被删")


def t_gen_host_keeps_exec(tmp):
    cfg = {"docgen": {"ag": {"file": "tool.sh", "builtin": "agents-entry"}}}
    root = mk(tmp, "exec", cfg, [("tool.sh", "#!/bin/sh\n<!-- GEN:ag BEGIN -->\n<!-- GEN:ag END -->\n")], first_commit=False)
    git(root, "add", "-A")
    git(root, "update-index", "--chmod=+x", "tool.sh")
    commit(root)
    expect(git(root, "ls-files", "-s", "tool.sh").stdout.startswith("100755"), "②b 带 GEN 段的可执行脚本刷新后仍是 100755")
    expect("GEN:ag BEGIN" in git(root, "show", "HEAD:tool.sh").stdout and len(git(root, "show", "HEAD:tool.sh").stdout) > 80, "②b 前提:生成段被刷新进提交")


def t_gen_host_attr_skipped(tmp):
    cfg = {"docgen": {"ag": {"file": "doc.md", "builtin": "agents-entry"}}}
    stale = "# d\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    root = mk(tmp, "attr", cfg, [("doc.md", stale), (".gitattributes", "doc.md filter=nomessx\n")], first_commit=False)
    git(root, "add", "-A")
    p = commit(root)
    expect(p.returncode == 0 and "not refreshed" in p.stderr, "②b 设了 filter 的 GEN 文件应跳过并报黄: " + p.stderr)
    expect(git(root, "show", "HEAD:doc.md").stdout.replace("\r", "") == stale, "②b 跳过的文件原样提交")


def t_gen_host_dirty_skipped(tmp):
    cfg = {"docgen": {"ag": {"file": "doc.md", "builtin": "agents-entry"}}}
    stale = "# d\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    root = mk(tmp, "dirty", cfg, [("doc.md", stale)], first_commit=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "stale", "--no-verify")
    draft = "# d EDITED\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    w(root, "doc.md", draft)  # 标记外的未暂存改动
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    p = commit(root)
    expect(p.returncode == 0 and "not refreshed" in p.stderr, "④ 有未暂存改动的 GEN 文件应跳过并报黄: " + p.stderr)
    expect(r(root, "doc.md") == draft and "doc.md" not in head_files(root), "④ 这段改动不在提交里、还在工作区")


def t_gen_host_assume_unchanged_skipped(tmp):
    cfg = {"docgen": {"ag": {"file": "doc.md", "builtin": "agents-entry"}}}
    stale = "# d\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    root = mk(tmp, "assume", cfg, [("doc.md", stale)], first_commit=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "stale", "--no-verify")
    git(root, "update-index", "--assume-unchanged", "doc.md")
    draft = "# d EDITED\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    w(root, "doc.md", draft)
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    p = commit(root)
    expect(p.returncode == 0 and "not refreshed" in p.stderr, "assume-unchanged 的 GEN 宿主有草稿应跳过并报黄: " + p.stderr)
    expect(r(root, "doc.md") == draft, "草稿没被覆盖")


def t_red_leaves_bytes_identical(tmp):
    root = mk(tmp, "bytes")
    w(root, "src/bad.py", BAD)
    w(root, "src/a.py", "# a\nx = 5\n")
    git(root, "add", "src/bad.py", "src/a.py")
    w(root, "docs/draft.md", "unstaged\n")
    before = digests(root)
    expect(commit(root).returncode != 0, "④ 前提:违规提交被挡")
    expect(digests(root) == before, "④ 检查报红时索引和工作区应与提交前逐字节相同")


def t_commit_msg_rejects(tmp):
    root = mk(tmp, "cmsg")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    w(root, ".git/hooks/commit-msg", "#!/bin/sh\nexit 1\n")
    expect(commit(root).returncode != 0, "②c 前提:commit-msg 拒绝")
    expect("docs/system-map/files.md" in git(root, "diff", "--cached", "--name-only").stdout.split(), "②c 普通提交被拒后生成物留在暂存区")
    git(root, "reset", "-q", "--hard")
    w(root, "src/a.py", "# renamed header\nx = 7\n")
    expect(git(root, "commit", "-aqm", "t", check=False).returncode != 0, "②c 前提:-a 被拒")
    expect("renamed header" in r(root, "docs/system-map/files.md"), "②c -a 被拒后生成物在工作区")


def t_merge(tmp):
    root = mk(tmp, "merge")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    git(root, "commit", "-qm", "feat work")
    git(root, "checkout", "-q", "main")
    w(root, "src/m.py", "# m\n")
    git(root, "add", "src/m.py")
    commit(root)
    git(root, "merge", "-q", "--no-ff", "--no-commit", "feat")
    p = git(root, "commit", "-qm", "merge feat", check=False)
    expect(p.returncode == 0 and "src/n.py" in r(root, "docs/system-map/files.md"), "③ 两步合并的收尾提交里应含刷新: " + p.stderr)
    expect("docs/system-map/files.md" in git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--first-parent", "HEAD").stdout.split(),
           "③ 刷新进了合并提交")


def t_merge_direct_blocked_and_cherry_pick_unchecked(tmp):
    root = mk(tmp, "mergebad")
    git(root, "checkout", "-qb", "bad")
    w(root, "src/bad.py", BAD)
    git(root, "add", "src/bad.py")
    git(root, "commit", "-qm", "bad", "--no-verify")
    git(root, "checkout", "-q", "main")
    w(root, "src/m.py", "# m\n")
    git(root, "add", "src/m.py")
    commit(root)
    expect(git(root, "merge", "--no-ff", "-m", "m", "bad", check=False).returncode != 0, "③ 直接 git merge --no-ff 带违规应被 pre-merge-commit 挡")
    git(root, "merge", "--abort", check=False)
    p = git(root, "cherry-pick", "bad", check=False)
    expect(p.returncode == 0 and "src/bad.py" in head_files(root), "③ cherry-pick 不查(固定现状): " + p.stderr)


def t_linked_worktree(tmp):
    root = mk(tmp, "wt")
    wt = os.path.join(tmp, "wt-linked")
    git(root, "worktree", "add", "-q", wt, "-b", "side")
    w(wt, "src/bad.py", BAD)
    git(wt, "add", "src/bad.py")
    expect(commit(wt).returncode != 0, "⑤ linked worktree 里提交应被查")


def t_submodule(tmp):
    sub = os.path.join(tmp, "subsrc")  # 子模块自己没有 nomess.json
    os.makedirs(sub)
    git(sub, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(sub, "config", k, v)
    w(sub, "lib.py", "# lib\n")
    git(sub, "add", "-A")
    git(sub, "commit", "-qm", "lib")
    parent = mk(tmp, "parent")
    git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", sub, "libs/sub")
    expect(commit(parent).returncode == 0, "⑤ 父仓库加子模块应通过(不读子模块内容)")
    inner = os.path.join(parent, "libs", "sub")
    git(inner, "config", "user.email", "t@t")
    git(inner, "config", "user.name", "t")
    nomess(inner, "hooks", "install")
    w(inner, "src/bad.py", BAD)
    git(inner, "add", "src/bad.py")
    expect(git(inner, "commit", "-qm", "inner", check=False).returncode == 0, "⑤ 子模块自己没有 nomess.json 时不读父仓库的配置")


def t_install_foreign_hook(tmp):
    root = mk(tmp, "foreign", hooks=False, first_commit=False)
    w(root, ".git/hooks/pre-commit", "#!/bin/sh\nexit 0\n")
    p = nomess(root, "hooks", "install")
    expect(r(root, ".git/hooks/pre-commit") == "#!/bin/sh\nexit 0\n" and "nomess-hook" in p.stdout, "⑥ 已有别人的钩子:不覆盖并打出配方: " + p.stdout)
    expect(os.path.isfile(os.path.join(root, ".git", "hooks", "pre-merge-commit")), "⑥ 另一个阶段照装")


def t_launcher_odd_paths(tmp):
    plug = os.path.join(tmp, "插件 目录")
    shutil.copytree(SCRIPTS, os.path.join(plug, "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
    script = os.path.join(plug, "scripts", "nomess.py")
    root = mk(tmp, "odd", hooks=False)
    expect(nomess(root, "hooks", "install", script=script).returncode == 0, "⑥ 前提:从带空格和中文的目录安装")
    git(root, "checkout", "-qb", "feat")
    w(root, "src/bad.py", BAD)
    git(root, "add", "src/bad.py")
    expect(commit(root).returncode != 0, "⑥ 插件目录带空格和中文时启动器能跑(违规被挡)")
    shutil.rmtree(os.path.join(plug, "scripts"))
    p = commit(root)
    expect(p.returncode == 0 and "not checked" in p.stderr, "⑥ 启动器指向不存在的脚本:提交放行并打一行: " + p.stderr)


def guard(root, command, tool="Bash"):
    p = subprocess.run([sys.executable, GUARD], input=json.dumps({"cwd": root, "tool_name": tool, "tool_input": {"command": command}}),
                       capture_output=True, text=True, encoding="utf-8", env=ENV)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def denied(out):
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def t_guard(tmp):
    root = mk(tmp, "guard")
    for cmd in ("git commit --no-verify -m x", "git commit -nm x", "git -c core.hooksPath=x commit -m x", "git config core.hooksPath x",
                "git commit -m ';' --no-verify", "git commit -m ticket#123 --no-verify"):
        expect(denied(guard(root, cmd)), "⑦ 应 deny: " + cmd)
    for cmd in ("git merge -n x", "git commit -m x", "git status", "git config --get core.hooksPath"):
        expect(not denied(guard(root, cmd)), "⑦ 不该 deny: " + cmd)
    expect(denied(guard(root, "git commit -nm x", "PowerShell")), "⑦ PowerShell 同样 deny")
    expect(denied(guard(root, r'& "C:\Program Files\Git\bin\git.exe" commit --no-verify', "PowerShell")), "⑦ PowerShell 调用运算符 + 带路径 git 应 deny")
    os.remove(os.path.join(root, ".git", "hooks", "pre-merge-commit"))
    expect(not denied(guard(root, "git merge --no-ff --no-commit topic")), "⑦ 只接了 pre-commit 时 --no-commit 的合并放行")
    expect(denied(guard(root, "git merge --no-ff topic")), "⑦ 没接 pre-merge-commit 的真合并应 deny")
    expect(not denied(guard(tmp, "git commit --no-verify -m x")), "⑦ 没有 nomess.json 的目录放行")
    os.remove(os.path.join(root, ".git", "hooks", "pre-commit"))
    expect(denied(guard(root, "git commit -m x")), "⑦ 钩子文件被删后的提交应 deny")
    nomess(root, "hooks", "install")
    w(root, ".git/nomess-hook", r(root, ".git/nomess-hook").replace(nm_config_self(), "/old/plugin/nomess.py"))
    guard(root, "git commit -m x")
    expect(nm_config_self() in r(root, ".git/nomess-hook"), "⑦ 启动器路径过期应被重写")


def nm_config_self():
    return os.path.join(SCRIPTS, "nomess.py").replace("\\", "/")


def t_guard_parse(tmp):
    """guard 的命令解析(纯函数,不起 git):(命令, 应挡的绕过写法或 None, 目标目录)。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nm_guard", GUARD)
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    base = os.path.join(tmp, "base")
    for cmd, why, d in (('git commit -nm"fix 2"', "-n", base),
                        ("git.exe commit --no-verify", "--no-verify", base),
                        ('git commit -m "Document --no-verify"', None, base),
                        ("git commit -m x -- -n", None, base),
                        ('cd "中文 项目" && git commit --no-verify', "--no-verify", os.path.join(base, "中文 项目"))):
        got = [c for c in g.calls(cmd, base) if c[1] == "commit"]
        expect(got == [(d, "commit", why)], "⑦ 解析 %s: %r" % (cmd, got))


def t_ita_not_in_tree(tmp):
    root = mk(tmp, "ita")
    git(root, "checkout", "-qb", "feat")
    w(root, "docs/target.md", "# t\n")
    git(root, "add", "-N", "docs/target.md")
    w(root, "docs/a.md", "[t](target.md)\n")
    git(root, "add", "docs/a.md")
    p = commit(root)
    expect(p.returncode != 0 and "docs/a.md" in p.stderr, "① git add -N 的占位条目不进提交:链接它的文档应被断链挡住: " + p.stderr)


def t_gen_host_crlf_clean(tmp):
    cfg = {"docgen": {"ag": {"file": "doc.md", "builtin": "agents-entry"}}}
    stale = "# d\n<!-- GEN:ag BEGIN -->\nold\n<!-- GEN:ag END -->\n"
    root = mk(tmp, "crlf", cfg, [("doc.md", stale)], first_commit=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "stale", "--no-verify")
    git(root, "config", "core.autocrlf", "true")
    os.remove(os.path.join(root, "doc.md"))
    git(root, "checkout", "--", "doc.md")
    expect("\r\n" in r(root, "doc.md"), "④ 前提:autocrlf 检出的宿主文件是 CRLF")
    w(root, "src/n.py", "# n\n")
    git(root, "add", "src/n.py")
    p = commit(root)
    expect(p.returncode == 0 and "not refreshed" not in p.stderr, "④ autocrlf 下干净的 CRLF 宿主文件不算有未暂存改动: " + p.stderr)
    expect("doc.md" in head_files(root) and "\nold\n" not in git(root, "show", "HEAD:doc.md").stdout, "④ 生成段刷新进了提交")
    expect(clean(root), "④ 刷新后工作区干净: " + git(root, "status", "--porcelain").stdout)


def t_atomic_write_keeps_mode(tmp):
    p = os.path.join(tmp, "x", "tool.sh")
    os.makedirs(os.path.dirname(p))
    w(tmp, "x/tool.sh", "old\n")
    os.chmod(p, 0o755)
    nm_config.atomic_write(p, "new\n")
    expect(r(tmp, "x/tool.sh") == "new\n" and os.listdir(os.path.dirname(p)) == ["tool.sh"], "原子写:内容换了、没有残留临时文件")
    if os.name != "nt":  # Windows 上没有可执行位
        expect(stat.S_IMODE(os.stat(p).st_mode) == 0o755, "原子写:替换已有文件保留原权限")


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-gh-")
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("t_") and callable(fn) and (not sys.argv[1:] or name in sys.argv[1:]):  # 命令行可只跑指定的用例
                print("-- " + name)
                try:
                    fn(tmp)
                except Exception as e:  # noqa: BLE001 测试脚本:任何异常都算这条失败
                    fails.append("%s 抛异常: %s" % (name, e))
                    print("   ERROR: %s" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if not fails else "FAILED:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
