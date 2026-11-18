"""P24 子系统间约束和依赖图的测试:每条在临时 git 仓库里真跑。只测读代码难推准、又容易回归的边界行为;
其余验收在交回里写"读代码确认"。全过打印 OK,否则列出失败项并退出码 1。可在命令行只跑指定的用例(t_ 开头的函数名)。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo, put  # noqa: E402
import check  # noqa: E402
import deps  # noqa: E402
import map as nm_map  # noqa: E402
import snapshot  # noqa: E402


def git(root, *a):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p.stdout.strip()


def commit(root):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "c")


def cfg_put(root, cfg):
    put(root, "nomess.json", json.dumps(dict({"format": "nomess/1", "main_branch": "main", "lang": "en"}, **cfg)))


def run(root):
    """工作区对 HEAD(没有提交时对空),和手动 nomess check 一样。"""
    with snapshot.open_snapshot(root, "worktree") as cand:
        base = snapshot.open_snapshot(root, "tree", "HEAD") if snapshot.has_commit(root, "HEAD") else None
        try:
            return check.evaluate(cand, base, exec_cmd=True, full=True)
        finally:
            if base:
                base.close()


def rules(res, *ids):
    return [f for f in res["findings"] if f["rule"] in ids]


PY_CYCLE = [("a/x.py", "import b.y\n"), ("b/y.py", "from a import x\n")]


def t_a1_language(tmp):
    """① 只由 JS 或 C# 的边成的环报黄不报红;Python 边成的环报红。"""
    files = PY_CYCLE + [("c/p.js", "import q from '../d/q.js'\n"), ("d/q.js", "const p = require('../c/p.js')\n"),
                        ("e/E.cs", "namespace E1 {}\nusing F1;\n"), ("f/F.cs", "namespace F1 {}\nusing E1;\n")]
    root = mkrepo(tmp, "a1lang", {"size": "medium", "lang": "en"}, files)
    got = sorted((f["level"], tuple(f["k"])) for f in rules(run(root), "A1"))
    expect(got == [("red", ("a", "b")), ("yellow", ("c", "d")), ("yellow", ("e", "f"))], "A1 颜色按边的语言: %r" % got)


def t_cycle_only_a1(tmp):
    """② 跨子系统的环只报 A1,不再逐边报 A2 / A3(去掉环之后同样的边照报,证明不是没查)。"""
    cfg = {"size": "medium", "arch": {"layers": [["a"], ["b"]], "independent": ["a", "b"]}}
    root = mkrepo(tmp, "a1only", cfg, PY_CYCLE)
    res = run(root)
    expect([f["level"] for f in rules(res, "A1")] == ["red"] and not rules(res, "A2", "A3"),
           "环上只报 A1: %r" % [(f["rule"], f["k"]) for f in rules(res, "A1", "A2", "A3")])
    put(root, "a/x.py", "x = 1\n")
    got = sorted((f["rule"], tuple(f["k"])) for f in rules(run(root), "A1", "A2", "A3"))
    expect(got == [("A2", ("b", "a")), ("A3", ("b", "a"))], "没有环时 b -> a 报 A2、A3: %r" % got)


def t_edge_from_new_file(tmp):
    """③ 原有文件不变、新加仓库内的 helper.py 后依赖边出现(原始 import 进缓存,边每次现算)。"""
    root = mkrepo(tmp, "newhelper", {}, [("src/a.py", "import helper\n")])
    with snapshot.open_snapshot(root, "worktree") as snap:
        before = deps.edges(snap)
    put(root, "src/helper.py", "x = 1\n")
    with snapshot.open_snapshot(root, "worktree") as snap:
        after = deps.edges(snap)
    expect(not before and ("src/a.py", "src/helper.py") in after, "加 helper.py 后应出现边: %r -> %r" % (before, after))


def t_table_regex_change(tmp):
    """④ 只改抽取表正则、源码不动,抽取结果跟着变(缓存键带表配置的哈希)。"""
    root = mkrepo(tmp, "regex", {}, [("src/a.py", 'EV("x")\nON("y")\n')])
    spec = {"title": "t", "columns": ["v"], "glob": "src/*.py", "regex": r'EV\("(\w+)"\)'}
    with snapshot.open_snapshot(root, "worktree") as snap:
        one = nm_map.rows_of(snap, {"map": {"ev": spec}}, "ev")[1]
        two = nm_map.rows_of(snap, {"map": {"ev": dict(spec, regex=r'ON\("(\w+)"\)')}}, "ev")[1]
    expect(one == [["x", "src/a.py"]] and two == [["y", "src/a.py"]], "改正则后结果应变: %r / %r" % (one, two))


def t_loosen_arch_systems(tmp):
    """⑤ LOOSEN 表里 arch 和 systems 那几行:删一条 forbid -> B2 红、加一条 -> 不报;改 systems 的 glob -> B2 红。"""
    fb = {"from": "a", "to": "b", "why": "w"}
    base = {"systems": {"a": ["a/**"], "b": ["b/**"]}, "arch": {"forbid": [fb]}}
    root = mkrepo(tmp, "loosen", {}, [("a/x.py", "x = 1\n"), ("b/y.py", "y = 1\n")])
    cfg_put(root, base)
    commit(root)
    b2 = lambda: [f for f in rules(run(root), "B2") if f["level"] == "red"]  # noqa: E731
    cfg_put(root, dict(base, arch={"forbid": []}))
    expect(len(b2()) == 1, "删一条 forbid 应 B2 红")
    cfg_put(root, dict(base, arch={"forbid": [fb, {"from": "b", "to": "a", "why": "w"}]}))
    expect(not b2(), "加一条 forbid 不该报 B2")
    cfg_put(root, dict(base, systems={"a": ["a/*.py"], "b": ["b/**"]}))
    expect(len(b2()) == 1, "改 systems 的 glob 应 B2 红")


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-arch-")
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("t_") and callable(fn) and (not sys.argv[1:] or name in sys.argv[1:]):
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
