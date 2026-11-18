"""D1 复制粘贴的测试(P23):每条在临时 git 仓库里真跑 check.evaluate。其余(PL-DUP 不看生成段和代码块、缓存键带分析器版本)在交回里写读代码确认。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo, put  # noqa: E402
from test_ratchet import by, commit, run  # noqa: E402


def body(prefix, n=30):
    return "".join("    self.%s%d = load(%s%d, %d)\n" % (prefix, i, prefix, i, i) for i in range(n))


def distinct(n=40):
    return "".join("def f%d(x):\n    return x * %d + g%d(x)\n" % (i, i, i) for i in range(n))


def t_renamed_is_yellow(tmp):
    """② 只有字段名不同的两段相似代码:D1 报黄不报红。"""
    root = mkrepo(tmp, "renamed", {}, [("src/a.py", "def a(self):\n" + body("a")), ("src/b.py", "def b(self):\n" + body("b"))])
    d1 = by(run(root), "D1")
    expect(len(d1) == 1 and d1[0]["level"] == "yellow", "改名克隆应一条黄: %r" % [(f["file"], f["level"]) for f in d1])


def t_new_copy_of_old_file(tmp):
    """③ 新文件一字不差复制未改动的旧文件:只查改动文件时也要和全仓指纹比,判出红。"""
    root = mkrepo(tmp, "copy", {}, [("src/old.py", distinct()), ("src/other.py", "x = 1\n")])
    commit(root)
    put(root, "src/new.py", distinct())
    d1 = by(run(root), "D1")
    expect(len(d1) == 1 and d1[0]["level"] == "red" and d1[0]["state"] == "new" and "src/old.py" in [d1[0]["file"]] + d1[0].get("also", []),
           "应判出一条新增红 D1: %r" % d1)


def t_one_side_off(tmp):
    """④ 一边在关了 D1 的目录、一边不在:照报;两边都在关了的目录:不报。"""
    cfg = {"scopes": [{"paths": ["gen/**"], "checks": {"remove": ["D1"]}, "why": "generated"}]}
    root = mkrepo(tmp, "off", cfg, [("gen/old.py", distinct())])
    commit(root)
    put(root, "src/new.py", distinct())
    expect(len(by(run(root), "D1")) == 1, "src/new.py 复制 gen/old.py:一边开着,应报")
    root = mkrepo(tmp, "off2", cfg, [("gen/a.py", distinct()), ("gen/b.py", distinct())])
    expect(len(by(run(root), "D1")) == 0, "两边都在关了 D1 的目录:不报")


def t_min_tokens(tmp):
    """clone_tokens 低于下限 50:配置错误(ValueError,退出 2)。"""
    root = mkrepo(tmp, "min", {"smells": {"clone_tokens": 20}}, [("src/a.py", "x = 1\n")])
    try:
        run(root)
        expect(False, "clone_tokens=20 应抛 ValueError")
    except ValueError as e:
        expect("50" in str(e), "提示里要写明下限 50: %s" % e)


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-clones-")
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
