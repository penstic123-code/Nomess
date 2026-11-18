"""P25 plancheck 的测试:C4 重叠判定(glob 字面前缀比较)。其余验收在交回里写"读代码确认"。全过打印 OK,否则列出失败项并退出码 1。"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo, nm, put  # noqa: E402

SCHED = "| 包 | 依赖 | 状态 | 可改文件 |\n|---|---|---|---|\n%s\n"


def c4(tmp, name, rows):
    root = mkrepo(tmp, name, {"check": {"builtin": ["C4"]}}, [("docs/schedule.md", SCHED % "\n".join(rows))])
    p = nm(root, "check", "--json", "--all")
    return [i for i in json.loads(p.stdout) if i["rule"] == "C4"]


def t_c4_overlap(tmp):
    # 两个包都写 src/new/** 而目录不存在:只凭字面前缀推断 -> 黄(在做也是)
    f = c4(tmp, "new", ["| A | | 在做 | src/new/** |", "| B | | 在做 | src/new/**, docs/x.md |"])
    expect(len(f) == 1 and f[0]["level"] in ("yellow", "黄"), "两个在做包都写 src/new/** 只凭前缀推断应报一条黄: %r" % f)
    # 两边写同一条字面路径:确定重叠 -> 红
    f = c4(tmp, "lit", ["| A | | 在做 | src/new.py |", "| B | | 在做 | src/new.py |"])
    expect(len(f) == 1 and f[0]["level"] in ("red", "红"), "两个在做包写同一条字面路径应报红: %r" % f)
    # 排期里的花括号 glob 不报错、和另一个包的具体文件按花括号展开比
    f = c4(tmp, "brace", ["| A | | 在做 | src/{a,b}.py |", "| B | | 在做 | src/b.py |"])
    expect(len(f) == 1 and f[0]["level"] in ("red", "红"), "src/{a,b}.py 与 src/b.py 应正常报一条红(不再抛错): %r" % f)
    # src/*.py 和 src/*.js 不可能重叠:不报红
    f = c4(tmp, "ext", ["| A | | 在做 | src/*.py |", "| B | | 在做 | src/*.js |"])
    expect(not [i for i in f if i["level"] in ("red", "红")], "src/*.py 和 src/*.js 不应报红: %r" % f)
    # src/a/** 和 src/ab.py 不重叠
    f = c4(tmp, "ab", ["| A | | 在做 | src/a/** |", "| B | | 在做 | src/ab.py |"])
    expect(not f, "src/a/** 和 src/ab.py 不算重叠: %r" % f)


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
