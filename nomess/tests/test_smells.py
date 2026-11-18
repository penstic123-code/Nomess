"""P1 边界表和 S1 / S2 / P2 / P5 的冒烟测试(P23):在临时 git 仓库里真跑 check.evaluate。其余正反例在交回里写读代码确认。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo  # noqa: E402
from test_ratchet import by, run  # noqa: E402

P1_CASES = '''def a():
    try:
        x()
    except:
        cleanup()
        raise


def b():
    try:
        x()
    except Exception:
        pass  # ignore


def c():
    try:
        x()
    except OSError:
        pass


def d():
    try:
        x()
    except (OSError, BaseException):
        ...


def e():
    for i in z:
        try:
            x()
        except ValueError:
            continue
'''


def t_p1_table(tmp):
    """① P1 边界:`except: cleanup(); raise` 不报、`except Exception: pass  # ignore` 红、`except OSError: pass` 黄。"""
    root = mkrepo(tmp, "p1", {}, [("src/a.py", P1_CASES)])
    got = sorted((f["line"], f["level"]) for f in by(run(root), "P1"))
    expect(got == [(12, "red"), (19, "yellow"), (26, "red"), (34, "yellow")], "P1 结果不对: %r" % got)


def t_other_rules(tmp):
    """S1、S2、P2、P5 各一条:要开的号经 check.builtin 写出。"""
    code = "def long_one():\n" + "    x = 1\n" * 5 + "\n\ndef make_v2():\n    pass  # TODO later\n"
    cfg = {"check": {"builtin": ["S1", "S2", "P2", "P5"]}, "smells": {"file_lines": 5, "func_lines": 4}}
    root = mkrepo(tmp, "other", cfg, [("src/m.py", code), ("src/m_old.py", "y = 1\n")])
    res = run(root)
    expect([(f["file"], f["level"]) for f in by(res, "S1")] == [("src/m.py", "red")], "S1: %r" % by(res, "S1"))
    expect([(f["line"], f["k"]) for f in by(res, "S2")] == [(1, ["long_one"])], "S2 起行和全名: %r" % by(res, "S2"))
    expect([f["file"] for f in by(res, "P2")] == ["src/m.py"], "P2: %r" % by(res, "P2"))
    expect(sorted((f["file"], f["k"]) for f in by(res, "P5")) == [("src/m.py", ["make_v2"]), ("src/m_old.py", ["@file"])], "P5: %r" % by(res, "P5"))


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-smells-")
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
