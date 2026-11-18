"""snapshot.py 的测试:真 git 临时仓库,三种来源读到的文件清单、模式、内容各自正确。全过打印 OK,否则列出失败项并退出码 1。"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "scripts")))
import snapshot  # noqa: E402

fails = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def expect(cond, what):
    if not cond:
        fails.append(what)
        print("   FAIL: " + what)


def git(cwd, *a, **kw):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, **kw)


def w(root, p, data):
    full = os.path.join(root, p)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)


tmp = tempfile.mkdtemp()
try:
    git(tmp, "init", "-q")
    git(tmp, "config", "user.email", "t@t")
    git(tmp, "config", "user.name", "t")
    git(tmp, "config", "core.autocrlf", "false")
    w(tmp, "a.txt", b"v1\n")
    w(tmp, "dir/b.py", "中文\n".encode())
    w(tmp, "run.sh", b"#!/bin/sh\n")
    w(tmp, ".gitignore", b"ignored.txt\n")
    git(tmp, "add", "-A")
    git(tmp, "update-index", "--chmod=+x", "run.sh")
    # 符号链接和子模块记录直接写进索引(Windows 上建真符号链接不可靠)
    blob = git(tmp, "hash-object", "-w", "--stdin", input=b"a.txt").stdout.decode().strip()
    git(tmp, "update-index", "--add", "--cacheinfo", "120000,%s,link" % blob)
    git(tmp, "update-index", "--add", "--cacheinfo", "160000,%s,sub" % ("1" * 40))
    git(tmp, "commit", "-qm", "c1")
    # 提交之后:暂存一个改动、工作区再改、新增未跟踪和被忽略的文件、删掉一个已跟踪文件
    w(tmp, "a.txt", b"v2 staged\n")
    git(tmp, "add", "a.txt")
    w(tmp, "a.txt", b"v3 draft\n")
    w(tmp, "new.txt", b"untracked\n")
    w(tmp, "ignored.txt", b"x\n")
    os.remove(os.path.join(tmp, "dir", "b.py"))

    expect(os.path.samefile(snapshot.toplevel(tmp), tmp), "toplevel")
    expect(os.path.samefile(snapshot.toplevel(os.path.join(tmp, "dir")), tmp), "toplevel 从子目录")

    with snapshot.open_snapshot(tmp, "tree", "HEAD") as s:
        f = s.files()
        expect(f["run.sh"] == "100755" and f["a.txt"] == "100644", "tree 模式")
        expect(f["link"] == "120000" and f["sub"] == "160000", "tree 符号链接 / 子模块模式")
        expect(s.read("a.txt") == b"v1\n" and s.text("dir/b.py") == "中文\n", "tree 内容(HEAD,不受工作区影响)")
        expect(s.read("link") is None and s.read("sub") is None and s.read("nope") is None, "非普通文件 / 不存在读 None")
        expect(s.read("a.txt") == b"v1\n", "cat-file 复用连续读")

    with snapshot.open_snapshot(tmp, "index") as s:
        f = s.files()
        expect(s.read("a.txt") == b"v2 staged\n", "index 读暂存内容,不读工作区草稿")
        expect("new.txt" not in f and "ignored.txt" not in f, "index 不含未跟踪")
        expect("dir/b.py" in f and s.text("dir/b.py") == "中文\n", "index 含工作区已删的文件")

    with snapshot.open_snapshot(tmp, "worktree") as s:
        f = s.files()
        expect(s.read("a.txt") == b"v3 draft\n", "worktree 读磁盘")
        expect("new.txt" in f and "ignored.txt" not in f, "worktree 含未跟踪、尊重 .gitignore")
        expect("dir/b.py" not in f, "worktree 不含已删")
        expect(f["a.txt"] in snapshot.REGULAR, "worktree 模式")

    # 索引来源沿用 GIT_INDEX_FILE
    alt = os.path.join(tmp, "alt-index")
    subprocess.run(["git", "read-tree", "HEAD"], cwd=tmp, env=dict(os.environ, GIT_INDEX_FILE=alt), check=True)
    old = os.environ.get("GIT_INDEX_FILE")
    os.environ["GIT_INDEX_FILE"] = alt
    try:
        with snapshot.open_snapshot(tmp, "index") as s:
            expect(s.read("a.txt") == b"v1\n", "index 沿用 GIT_INDEX_FILE")
    finally:
        if old is None:
            del os.environ["GIT_INDEX_FILE"]
        else:
            os.environ["GIT_INDEX_FILE"] = old
        os.remove(alt)

    # core.fileMode=false:工作区里已跟踪文件的模式取索引的,可执行位不丢
    git(tmp, "config", "core.fileMode", "false")
    with snapshot.open_snapshot(tmp, "worktree") as s:
        expect(s.files()["run.sh"] == "100755", "worktree 在 core.fileMode=false 时取索引模式")

    # 改动列表
    with snapshot.open_snapshot(tmp, "index") as s:
        expect(s.changed() == {"a.txt": "M"}, "index changed: %r" % s.changed())
    with snapshot.open_snapshot(tmp, "worktree") as s:
        expect(s.changed() == {"a.txt": "M", "dir/b.py": "D", "new.txt": "A", "link": "D", "sub": "D"}, "worktree changed: %r" % s.changed())
    with snapshot.open_snapshot(tmp, "tree", "HEAD") as s:
        expect(s.changed() == {}, "tree 对自己无改动")
        expect(set(s.changed("HEAD~5").values()) == {"A"} and "a.txt" in s.changed("HEAD~5"), "base 不存在全部算 A")

    # 叠加
    with snapshot.open_snapshot(tmp, "index") as base:
        o = base.overlay({"a.txt": b"over\n", "run.sh": None, "gen/n.md": b"n\n", "ghost": None})
        f = o.files()
        expect(o.read("a.txt") == b"over\n" and o.text("gen/n.md") == "n\n", "overlay 新增 / 替换内容")
        expect("run.sh" not in f and o.read("run.sh") is None, "overlay 删除")
        expect(f["gen/n.md"] == "100644" and f["a.txt"] == "100644", "overlay 新文件 100644")
        expect(o.text("dir/b.py") == "中文\n", "overlay 未改动的文件读父快照")
        expect(base.read("a.txt") == b"v2 staged\n" and "run.sh" in base.files(), "overlay 不改父快照")
        expect(o.changed() == {"a.txt": "M", "gen/n.md": "A", "run.sh": "D"}, "overlay changed: %r" % o.changed())
        o2 = base.overlay({"run.sh": b"#!/bin/sh\nx\n"})
        expect(o2.files()["run.sh"] == "100755", "overlay 替换沿用原模式")
        o3 = o2.overlay({"dir/b.py": None})
        expect("dir/b.py" not in o3.files() and o3.read("run.sh") == b"#!/bin/sh\nx\n", "overlay 可再叠加")

    # 重命名不认:旧路径 D + 新路径 A
    git(tmp, "add", "-A")
    git(tmp, "commit", "-qm", "c2")
    git(tmp, "mv", "run.sh", "run2.sh")
    git(tmp, "commit", "-qm", "c3")
    with snapshot.open_snapshot(tmp, "tree", "HEAD") as s:
        expect(s.changed("HEAD~1") == {"run.sh": "D", "run2.sh": "A"}, "重命名: %r" % s.changed("HEAD~1"))

    for bad in (("tree", None), ("index", "HEAD"), ("x", None)):
        try:
            snapshot.open_snapshot(tmp, *bad)
            expect(False, "非法参数应抛 ValueError %r" % (bad,))
        except ValueError:
            pass
    nogit = tempfile.mkdtemp()
    try:
        snapshot.toplevel(nogit)
        expect(False, "非仓库应抛 SnapshotError")
    except snapshot.SnapshotError:
        pass
    finally:
        shutil.rmtree(nogit, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if not fails else "FAILED: %d" % len(fails))
sys.exit(1 if fails else 0)
