"""R1 教训检索和外部来源的测试:别名命中、外部来源条目不进规则文件、按文件查询带出直接依赖模块(不带反向)的条目。
全过打印 OK,否则列出失败项并退出码 1。可在命令行只跑指定的用例(t_ 开头的函数名)。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helpers import expect, fails, mkrepo, nm  # noqa: E402


def entry(title, extra):
    return "## %s\nWhen: x\nStatus: verified\n%s\n" % (title, extra)


LIB = ("docs/lessons/core.md", "# lessons\n\n"
       + entry("Persistence", "Aliases: 存档, save game\nWhat: flush on exit")
       + "\n" + entry("Net rule", "Paths: b/**\nRule: no blocking\nWhat: n")
       + "\n" + entry("Ui rule", "Paths: c/**\nRule: no globals\nWhat: u")
       + "\n" + entry("Web tip", "Paths: a/**\nRule: tip\nSource: external https://x\nWhat: w"))
FILES = [("a/x.py", "import b.y\n"), ("b/y.py", "X = 1\n"), ("c/z.py", "import a.x\n"), LIB]


def t_alias(tmp):
    """别名和标题同权重:标题里没有的词,别名里有就能查到。"""
    root = mkrepo(tmp, "alias", {"lang": "en"}, FILES)
    out = nm(root, "lessons", "find", "存档").stdout
    expect("Persistence" in out, "别名应命中: %r" % out)


def t_external_not_in_rules(tmp):
    """外部来源条目哪怕状态是已核实也不生成规则文件;同库里的非外部条目照常生成。"""
    root = mkrepo(tmp, "ext", {"lang": "en"}, FILES)
    expect(nm(root, "rules").returncode == 0, "rules 应成功")
    d = os.path.join(root, ".claude", "rules", "nomess")
    text = "".join(open(os.path.join(d, n), encoding="utf-8").read() for n in os.listdir(d))
    expect("no blocking" in text and "tip" not in text.replace("no blocking", ""), "外部条目不该进规则文件: %r" % text)


def t_add_external(tmp):
    """add --external 写来源行并强制未核实;-k 写别名。"""
    root = mkrepo(tmp, "addext", {"lang": "en"}, FILES)
    nm(root, "lessons", "add", "From web", "-s", "s", "-b", "b", "-k", "网页", "--external", "https://y")
    text = open(os.path.join(root, "docs", "lessons", "inbox.md"), encoding="utf-8").read()
    expect("Source: external https://y" in text and "Status: unverified" in text and "Aliases: 网页" in text, "add --external 的写法: %r" % text)


def t_find_by_file(tmp):
    """按文件查询:直接依赖(b)的条目带出并标 [依赖 b],反向依赖(c)的不带。"""
    root = mkrepo(tmp, "byfile", {"lang": "en", "systems": {"a": ["a/**"], "b": ["b/**"], "c": ["c/**"]}}, FILES)
    out = nm(root, "lessons", "find", "a/x.py").stdout
    expect("Net rule" in out and "[depends on b]" in out, "应带出依赖模块的条目: %r" % out)
    expect("Ui rule" not in out, "不该带出反向依赖的条目: %r" % out)
    expect("Web tip" in out, "路径 glob 命中的条目应排在里面: %r" % out)


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-lessons-find-")
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
