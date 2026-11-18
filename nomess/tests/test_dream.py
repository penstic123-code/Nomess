"""R3 自动整理(scripts/dream.py)的测试:触发条件的边界、锁、落地护栏、主检出保护、落地后一个 git revert 完全撤回。全过打印 OK,否则列出失败项并退出码 1。
用临时 git 仓库;记忆目录用临时目录,经 CLAUDE_CONFIG_DIR 下 settings.json 的 autoMemoryDirectory 定位。"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import digest, expect, fails, mkrepo, put, read  # noqa: E402
import dream  # noqa: E402

CORE = "# 教训\n\n## 旧坑\n概述: 何时 x\n状态: 已核实\n更新: 2026-01-01\n内容: 细节一\n"
EXT = "# 外部\n\n## 外部的坑\n概述: 何时 y\n状态: 未核实\n来源: 外部 http://example.invalid\n更新: 2026-01-01\n内容: 来自网页\n"
INBOX = "# inbox\n\n## 新的\n概述: s\n状态: 已核实\n更新: 2026-01-01\n内容: b\n"


def git(root, *a):
    p = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p.stdout.strip()


def commit_all(root, msg="c"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", msg)
    return git(root, "rev-parse", "HEAD")


def setup(tmp, name):
    """有 inbox 一条(lessons_remind 设 1,所以到线)的仓库 + 临时记忆目录;返回 (root, 记忆目录)。"""
    root = mkrepo(tmp, name, {"lessons_remind": 1, "dream": {"auto": True}}, [("docs/lessons/core.md", CORE), ("docs/lessons/ext.md", EXT), ("docs/lessons/inbox.md", INBOX)])
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "core.autocrlf", "false")
    commit_all(root)
    cfg, mem = os.path.join(tmp, name + "-cfg"), os.path.join(tmp, name + "-cfg", "mem")  # 记忆目录要在配置目录下才会自动 git init
    os.makedirs(mem)
    put(mem, "MEMORY.md", "- [页](a.md) — 何时用\n")
    put(mem, "a.md", "## a\n")
    put(cfg, "settings.json", json.dumps({"autoMemoryDirectory": mem}))
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    return root, mem


def run(root, *args):
    """在 root 下跑 dream.main,返回 (退出码, 输出)。"""
    old, buf = os.getcwd(), io.StringIO()
    os.chdir(root)
    try:
        with contextlib.redirect_stdout(buf):
            rc = dream.main(list(args))
    finally:
        os.chdir(old)
    print("$ dream %s -> %d\n   %s" % (" ".join(args), rc, buf.getvalue().strip().replace("\n", "\n   ")[:500]))
    return rc, buf.getvalue()


def state_path(root):
    return os.path.join(dream._common(root), dream.STATE)


def wt(root):
    return os.path.join(root, ".nomess", "dream")


def expect_discarded(root, out, head, what):
    expect("已丢弃" in out, "%s:应丢弃: %r" % (what, out))
    expect(git(root, "rev-parse", "HEAD") == head, "%s:HEAD 不该动" % what)
    expect(not os.path.isdir(wt(root)) and not os.path.exists(os.path.join(dream._common(root), dream.LOCK)), "%s:worktree 和锁应清掉" % what)
    expect(json.load(open(state_path(root), encoding="utf-8"))["last_attempt"] == dream._today(), "%s:应记一次尝试" % what)


def t_due_edges(tmp):
    root, _ = setup(tmp, "due")
    expect(dream.due(root), "有信号、没有状态时应触发")
    git(root, "checkout", "-q", "--detach")
    expect(not dream.due(root), "分离头指针不触发")
    git(root, "checkout", "-q", "-")
    run(root, "begin")
    run(root, "abort")  # 记一次尝试:今天 + 当前指纹
    expect(not dream.due(root), "1 天内不重复")
    st = json.load(open(state_path(root), encoding="utf-8"))
    st["last_attempt"] = "2000-01-01"
    put(os.path.dirname(state_path(root)), dream.STATE, json.dumps(st))
    expect(not dream.due(root), "指纹没变不触发")
    st["next_check"] = "2000-01-02"
    put(os.path.dirname(state_path(root)), dream.STATE, json.dumps(st))
    expect(dream.due(root), "指纹没变但已过 next_check 应重新判断(这里有信号,触发)")
    st["next_check"] = ""
    put(os.path.dirname(state_path(root)), dream.STATE, json.dumps(st))
    put(root, "docs/lessons/inbox.md", INBOX + "\n## 又一条\n概述: s\n状态: 已核实\n更新: 2026-01-01\n内容: b\n")
    commit_all(root)
    expect(dream.due(root), "内容变了、隔天、有信号应触发")
    st["backlog"] = True
    st["fingerprint"] = "x"
    put(os.path.dirname(state_path(root)), dream.STATE, json.dumps(st))
    put(root, "docs/lessons/inbox.md", "")
    commit_all(root)
    expect(dream.due(root), "backlog 为真算到线")
    expect(dream.take_summary(root) is None, "没有总结时返回 None")


def t_lock_busy(tmp):
    root, _ = setup(tmp, "lock")
    rc, _ = run(root, "begin")
    expect(rc == 0 and os.path.isdir(wt(root)), "begin 应建 worktree")
    rc, out = run(root, "begin")
    expect(rc == 3 and len(out.strip().splitlines()) == 1, "锁被占应立刻退出 3、一行说明")
    run(root, "abort")
    expect(not os.path.isdir(wt(root)), "abort 应删 worktree")


def t_guard_config(tmp):
    root, _ = setup(tmp, "gcfg")
    head = git(root, "rev-parse", "HEAD")
    run(root, "begin")
    put(wt(root), "nomess.json", read(root, "nomess.json").replace('"lessons_remind": 1', '"lessons_remind": 99'))
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "改 nomess.json")
    expect("nomess.json" in out, "worktree 里改了 nomess.json 应在 refresh 之前就丢弃: %r" % out)


def t_guard_external(tmp):
    root, _ = setup(tmp, "gext")
    head = git(root, "rev-parse", "HEAD")
    run(root, "begin")
    put(wt(root), "docs/lessons/ext.md", EXT.replace("未核实", "已核实"))
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "外部条目转正")
    expect("外部的坑" in out, "原因应点名条目: %r" % out)


def t_main_dirty_and_staged(tmp):
    root, _ = setup(tmp, "gmain")
    head = git(root, "rev-parse", "HEAD")
    run(root, "begin")
    put(wt(root), "docs/lessons/core.md", CORE.replace("细节一", "细节二"))
    mine = put(root, "docs/lessons/core.md", CORE + "我的未提交改动\n")
    before = digest(mine)
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "主检出同文件有未提交改动")
    expect("未提交改动" in out, "应是脚本自己查出的(不是 git 报错): %r" % out)
    expect(digest(mine) == before, "主检出文件应逐字节不变")
    expect(git(root, "diff", "--cached", "--name-only") == "", "不该动暂存区")
    # 已暂存内容
    git(root, "checkout", "--", "docs/lessons/core.md")
    run(root, "begin")
    put(wt(root), "docs/lessons/core.md", CORE.replace("细节一", "细节二"))
    other = put(root, "src/x.py", "x = 1\n")
    git(root, "add", "src/x.py")
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "主检出有已暂存内容")
    expect("暂存" in out, "应是脚本自己查出的: %r" % out)
    expect(git(root, "diff", "--cached", "--name-only") == "src/x.py" and os.path.isfile(other), "暂存的内容应原样留着")


def t_land_and_revert(tmp):
    root, mem = setup(tmp, "ok")
    orig = git(root, "rev-parse", "HEAD")
    rc, out = run(root, "begin")
    expect("[inbox]" in out and "新的" in out, "工作清单应列 inbox 标题: %r" % out)
    expect(os.path.isdir(os.path.join(mem, ".git")), "记忆目录应已 init 并存底")
    put(wt(root), "docs/lessons/core.md", CORE.replace("细节一", "细节二"))
    put(wt(root), "docs/lessons/inbox.md", "# inbox\n")  # 清空 inbox:inbox 里的条目已处理
    put(mem, "a.md", "## a\n改过\n")
    put(wt(root), ".nomess/dream-notes.md", "1. 外部的坑 等人核实\n")
    rc, out = run(root, "land")
    new = git(root, "rev-parse", "HEAD")
    expect(new != orig and git(root, "rev-parse", "HEAD~1") == orig, "应落地成一个新提交: %r" % out)
    expect("接管整理" in out and "git revert" in out and "dream-notes.md" in out, "第一次整理应用接管说法、带撤回命令和 notes 数: %r" % out)
    expect("细节二" in read(root, "docs/lessons/core.md"), "改动应落进主检出")
    expect(git(root, "status", "--porcelain", "--untracked-files=no") == "", "主检出应干净")
    expect(len(git(mem, "log", "--oneline").splitlines()) == 2, "记忆应有存底和整理两次提交")
    expect(os.path.isfile(os.path.join(root, ".nomess", "dream-notes.md")), "notes 应收到主检出的 .nomess/ 下")
    expect(dream.take_summary(root) == out.strip() and dream.take_summary(root) is None, "总结应存下、取一次就清")
    git(root, "revert", "--no-edit", "HEAD")
    expect(git(root, "diff", orig, "HEAD", "--stat") == "", "一个 git revert 应完全撤回")


def t_tiers(tmp):
    """13.13:改对外文档 -> 整次丢弃;新增开发者文档 -> 丢弃;修改已有开发者文档 -> 落地。"""
    root, _ = setup(tmp, "tiers")
    put(root, "README.md", "# r\n")
    put(root, "CONTRIBUTING.md", "# c\n")
    head = commit_all(root)
    for rel, text, what in (("README.md", "# r\n改\n", "改对外文档"), ("HACKING.md", "# h\n", "新增开发者文档")):
        run(root, "begin")
        put(wt(root), rel, text)
        rc, out = run(root, "land")
        expect_discarded(root, out, head, what)
    run(root, "begin")
    expect(not dream.may_edit(root, os.path.join(wt(root), "readme.md")), "大小写不同也认得出对外文档,不可写")
    if os.name == "nt":  # 大小写不敏感的文件系统:rel 取磁盘上的真实大小写,dev glob 仍命中
        expect(dream.may_edit(root, os.path.join(wt(root).upper(), "contributing.md")), "Windows 大小写不同的已有开发者文档可写")
    put(wt(root), "CONTRIBUTING.md", "# c\n改\n")
    rc, out = run(root, "land")
    expect(git(root, "rev-parse", "HEAD") != head and "改" in read(root, "CONTRIBUTING.md"), "修改开发者文档应落地: %r" % out)


def t_guard_retitle_and_ext(tmp):
    root, _ = setup(tmp, "gret")
    head = git(root, "rev-parse", "HEAD")
    run(root, "begin")
    put(wt(root), "docs/lessons/ext.md", EXT.replace("外部的坑", "改名的坑").replace("未核实", "已核实"))
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "外部条目改标题并转正")
    run(root, "begin")
    put(wt(root), "docs/x.py", "x = 1\n")
    rc, out = run(root, "land")
    expect_discarded(root, out, head, "docs 下新增 .py")
    expect("docs/x.py" in out, "原因应点名路径: %r" % out)


def t_midgit(tmp):
    root, _ = setup(tmp, "mid")
    head = git(root, "rev-parse", "HEAD")
    run(root, "begin")
    put(wt(root), "docs/lessons/core.md", CORE.replace("细节一", "细节二"))
    mark = os.path.join(root, ".git", "CHERRY_PICK_HEAD")
    open(mark, "w").write(head + "\n")
    rc, out = run(root, "land")
    expect(os.path.isfile(mark), "用户自己的 CHERRY_PICK_HEAD 不该被我们 abort 掉")
    os.remove(mark)
    expect_discarded(root, out, head, "主检出有 CHERRY_PICK_HEAD")
    expect("git 操作" in out, "应是进行中操作的原因: %r" % out)
    run(root, "begin")
    put(wt(root), "docs/lessons/core.md", CORE.replace("细节一", "细节二"))
    os.makedirs(os.path.join(root, ".git", "rebase-merge"))
    rc, out = run(root, "land")
    expect(os.path.isdir(os.path.join(root, ".git", "rebase-merge")), "rebase-merge 不该被动")
    shutil.rmtree(os.path.join(root, ".git", "rebase-merge"))
    expect_discarded(root, out, head, "主检出在 rebase")


def t_mv_rm(tmp):
    root, _ = setup(tmp, "gmv")
    run(root, "begin")
    rc, _ = run(root, "mv", "docs/lessons/inbox.md", "docs/lessons/inbox2.md")
    expect(rc == 0 and os.path.isfile(os.path.join(wt(root), "docs/lessons/inbox2.md")), "mv 应成功")
    rc, _ = run(root, "mv", "docs/lessons/core.md", "AGENTS.md.bak")
    expect(rc == 2, "目标不可写应退出 2")
    rc, _ = run(root, "mv", "docs/lessons/core.md", "README.md")
    expect(rc == 2, "目标是对外文档(根 README)应退出 2")
    rc, _ = run(root, "rm", "nomess.json")
    expect(rc == 2, "rm 范围外应退出 2")
    rc, _ = run(root, "rm", "docs/lessons/ext.md")
    expect(rc == 0 and not os.path.exists(os.path.join(wt(root), "docs/lessons/ext.md")), "rm 应成功")
    run(root, "abort")
    rc, _ = run(root, "rm", "docs/lessons/core.md")
    expect(rc == 2, "没 begin 应退出 2")


def t_auto_default_off(tmp):
    """合起来审查 3a:配置没写 dream.auto(老项目)按关:有信号也不触发。"""
    root, _ = setup(tmp, "autooff")
    cfg = json.loads(read(root, "nomess.json"))
    del cfg["dream"]
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    commit_all(root)
    expect(not dream.due(root), "没写 dream.auto 不触发")


def t_strays_mv_and_memory(tmp):
    """合起来审查 2、4、5:根目录散落 .md 能 mv 进文档根;子系统里的、和源码同目录的不算接管候选;记忆目录里的 .md 能 mv / rm。"""
    import nm_config
    import snapshot
    root, _ = setup(tmp, "stray")
    put(root, "notes.md", "# 笔记\n")
    put(root, "src/a.py", "x = 1\n")
    put(root, "src/design.md", "# 子系统说明\n")
    put(root, "tools/run.sh", "echo\n")
    put(root, "tools/usage.md", "# 跟着脚本\n")
    commit_all(root)
    with snapshot.open_snapshot(root, "tree", "HEAD") as snap:
        got = dream.strays(snap, nm_config.expanded(nm_config.load_snapshot(snap)))
    expect(got == ["notes.md"], "接管候选只剩根目录的 notes.md: %r" % got)
    mem = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", "stray", "memory")  # 在配置目录的 projects/ 下才认
    put(mem, "MEMORY.md", "- [b](b.md)\n")
    put(mem, "b.md", "## b\n")
    put(os.environ["CLAUDE_CONFIG_DIR"], "settings.json", json.dumps({"autoMemoryDirectory": mem}))
    run(root, "begin")
    rc, _ = run(root, "mv", "notes.md", "docs/plans/notes.md")
    expect(rc == 0 and os.path.isfile(os.path.join(wt(root), "docs/plans/notes.md")), "散落 .md 应能挪进文档根")
    rc, _ = run(root, "mv", os.path.join(mem, "b.md"), os.path.join(mem, "topic", "c.md"))
    expect(rc == 0 and os.path.isfile(os.path.join(mem, "topic", "c.md")), "记忆目录里 mv 应成功")
    rc, _ = run(root, "mv", os.path.join(mem, "MEMORY.md"), os.path.join(root, "x.md"))
    expect(rc == 2 and os.path.isfile(os.path.join(mem, "MEMORY.md")), "记忆挪出记忆目录应拒绝")
    rc, _ = run(root, "rm", os.path.join(mem, "topic", "c.md"))
    expect(rc == 0 and not os.path.exists(os.path.join(mem, "topic", "c.md")), "记忆目录里 rm 应成功")
    run(root, "abort")


def t_guard_cmd(tmp):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
    import guard
    nm = guard.NOMESS[0]
    ok = lambda c, tool="Bash": guard.is_nomess_command(c, tool)
    expect(ok('python "%s" check' % nm) and ok('"%s" dream land' % nm) and ok('python "%s" init --auto --lang zh-CN' % nm), "白名单内应放行")
    expect(ok('python "%s" dream mv a.md b.md' % nm) and ok('python "%s" dream rm a.md' % nm) and not ok('python "%s" dream rm a.md b.md' % nm), "dream mv / rm 白名单")
    expect(not ok('python "%s" off' % nm) and not ok('python "%s" check --freeze' % nm) and not ok('python "%s" check --fre' % nm)
           and not ok('python "%s" hooks uninstall' % nm) and not ok('python "%s" refresh' % nm), "白名单外不放行")
    expect(not ok('& python "%s" check (Start-Process calc)' % nm, "PowerShell"), "PowerShell 子表达式不放行")
    expect(not ok('python "%s" check $env:X' % nm, "PowerShell") and not ok('python /tmp/evil/python "%s" check' % nm), "含 $ 或陌生解释器不放行")


def main():
    tmp = tempfile.mkdtemp()
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("t_") and callable(fn):
                print("-- " + name)
                try:
                    fn(tmp)
                except Exception as e:  # noqa: BLE001 测试脚本:任何异常都算这条失败
                    fails.append("%s 抛异常: %r" % (name, e))
                    print("   ERROR: %r" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if not fails else "FAILED:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
