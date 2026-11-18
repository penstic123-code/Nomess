"""一键验收:把 tests/fixture 拷到临时目录(git 仓库),逐项跑 nomess 各子命令。全过打印 OK,否则列出失败项并退出码 1。
--write-golden 重写 tests/golden.json;--timing 另查每条命令不超过 2 秒(只在本地看性能用,CI 不加:耗时受机器和调度影响)。"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from helpers import HERE, PLUGIN, digest, expect, fails, mkrepo, nm, put, read  # noqa: E402


def test_fixture(tmp):
    root = os.path.join(tmp, "repo")
    shutil.copytree(os.path.join(HERE, "fixture"), root)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    doc = os.path.join(root, "docs", "system-map.md")

    # 1 每种规则写法各一条报红;黄级和过时生成段报黄
    p = nm(root, "check", "--all")
    expect(p.returncode == 1, "check 应退出码 1")
    for tag in ("红 R1 src/a.py:3", "红 R2 src/b.py", "红 R3", "黄 R4 src/a.py:4", "黄 GEN"):
        expect(tag in p.stdout, "check 输出缺 " + tag)
    expect("src/c.py" not in p.stdout.split("R2")[0], "白名单 src/c.py 不该报 R1")
    expect("HDR" not in p.stdout, "HDR 缺省关(check.builtin 没写 HDR)")
    p = nm(root, "check", "--red")
    expect("黄" not in p.stdout.replace("黄 0", ""), "--red 不该出黄")
    p = nm(root, "check", "--json", "--all")
    items = json.loads(p.stdout)
    expect(all(set(i) == {"level", "rule", "file", "line", "msg", "state", "frozen"} for i in items) and any(i["rule"] == "R1" and i["line"] == 3 for i in items),
           "check --json 字段或内容不对")

    # 2 docgen:重写一次,再跑不改内容、不出声
    p = nm(root, "docgen", "--check")
    expect(p.returncode == 1, "docgen --check 应报过时")
    nm(root, "docgen")
    h = digest(doc)
    p = nm(root, "docgen")
    expect(p.stdout == "" and digest(doc) == h, "docgen 往返应不改内容且无输出")
    expect(nm(root, "docgen", "--check").returncode == 0, "重写后 docgen --check 应通过")
    text = read(root, "docs/system-map.md")
    expect("| A | 1 | src/a.py |" in text and "stamp 1" in text and "手写部分" in text, "生成内容或手写部分不对")

    # 3 基线:冻结后静默;新增违规只报新增;复制一行旧违规也算新增
    nm(root, "check", "--freeze")
    p = nm(root, "check")
    expect(p.returncode == 0 and p.stdout == "", "冻结后应静默通过")
    with open(os.path.join(root, "src", "b.py"), "a", encoding="utf-8") as f:
        f.write('print("new")\n')
    p = nm(root, "check")
    expect(p.returncode == 1 and "src/b.py:2" in p.stdout and "R2" not in p.stdout, "只应报新增的 b.py:2")
    with open(os.path.join(root, "src", "a.py"), "a", encoding="utf-8") as f:
        f.write('print("debug")\n')
    p = nm(root, "check", "--all")
    expect("红 R1 src/a.py:5" in p.stdout and "红 R1 src/a.py:3" not in p.stdout, "复制旧违规行应报新增(a.py:5),旧的是存量不报红")

    # 4 map:首页 + 分页;--check 往返
    p = nm(root, "map")
    expect(p.returncode == 0, "map 应成功")
    for f in ("index", "files", "deps", "modules"):
        expect(os.path.isfile(os.path.join(root, "docs", "system-map", f + ".md")), "缺 system-map/%s.md" % f)
    expect("| B | 2 | src/b.py |" in read(root, "docs/system-map/modules.md"), "modules.md 缺 B 行")
    expect("| src/a.py | " in read(root, "docs/system-map/files.md"), "files.md 缺 a.py")
    expect(nm(root, "map", "--check").returncode == 0, "map 后 --check 应通过")
    put(root, "src/d.py", "# 新文件\n")
    p = nm(root, "map", "--check")
    expect(p.returncode == 1 and "files.md" in p.stdout, "加文件后 map --check 应报 files.md 过时")
    expect("GEN docs/system-map/files.md" in nm(root, "check", "--all").stdout, "check 应报系统图过时")

    # 5 lessons:find / 路径分隔符 / add / --unverified 往返
    p = nm(root, "lessons", "find", "save.py")
    expect("改存档字段前先查兼容" in p.stdout and "(未核实)" not in p.stdout, "lessons find 应命中且无未核实标记")
    expect("改存档字段前先查兼容" in nm(root, "lessons", "find", "src\\save.py").stdout, "反斜杠路径应命中")
    expect(nm(root, "lessons", "find", "不存在的词").stdout == "", "无命中应静默")
    expect(not os.path.exists(os.path.join(root, "docs", "lessons", ".hits.json")), "find 不该写 .hits.json")
    nm(root, "lessons", "add", "测试教训", "-s", "改 foo 时适用", "-b", "做法")
    expect("inbox 1 条" in nm(root, "lessons", "status").stdout, "status 应 1 条")
    expect("状态: 已核实" in read(root, "docs/lessons/inbox.md"), "缺省应写已核实")
    nm(root, "lessons", "add", "猜的教训", "-s", "改 bar 时适用", "-b", "推测", "--unverified")
    expect("状态: 未核实" in read(root, "docs/lessons/inbox.md"), "--unverified 应写未核实")
    expect("猜的教训(未核实)" in nm(root, "lessons", "find", "bar").stdout, "find 应标出未核实")
    p = nm(root, "lessons", "status")
    expect("inbox 2 条" in p.stdout and "未核实 1 条" in p.stdout, "status 应报未核实 1 条")
    expect("黄 L1" in nm(root, "check", "--all").stdout, "check 应列未核实教训")

    # 6 记忆体检:软预算报黄,断链和多级目录报红;.git 不算子目录
    mem = os.path.join(tmp, "mem")
    os.makedirs(os.path.join(mem, "sub"))
    os.makedirs(os.path.join(mem, ".git"))
    put(mem, ".git/HEAD", "ref")
    put(mem, "MEMORY.md", "- [甲](a.md) — 何时用\n- [乙](gone.md) — 断链\n" + "- 填充" * 2500 + "\n")
    put(mem, "a.md", "## 条目\n见 [[不存在的页]]\n状态: 未核实\n")
    put(mem, "sub/deep.md", "## x\n")
    p = nm(root, "check", "--memory", mem)
    expect(p.returncode == 1, "记忆体检有红应退出码 1")
    for tag in ("黄 M2", "红 M5", "红 M4"):
        expect(tag in p.stdout, "memory 输出缺 " + tag)
    expect("M4 .git" not in nm(root, "check", "--memory", mem, "--all").stdout, ".git 不该报 M4")
    expect("黄 M6" in nm(root, "check", "--memory", mem, "--all").stdout, "记忆里的未核实应报 M6")

    # 7 status
    p = nm(root, "status")
    expect(p.returncode == 0 and "inbox 2 条" in p.stdout, "status 文本不对")
    s = json.loads(nm(root, "status", "--json").stdout)
    expect(set(s) == {"stale", "memory_over", "inbox", "memory_dir", "memory_source", "memory_problem", "lessons_dir", "suggest"}
           and s["inbox"] == 2 and s["stale"] >= 1, "status --json 内容不对: %r" % s)


def test_config(tmp):
    # 缺 main_branch / review.level 非法:报错退出 2;BOM 配置能读
    root = mkrepo(tmp, "cfg", {})
    cfgp = os.path.join(root, "nomess.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    del cfg["main_branch"]
    put(root, "nomess.json", json.dumps(cfg))
    p = nm(root, "lessons", "status")
    expect(p.returncode == 2 and "main_branch" in p.stderr, "缺 main_branch 应报错退出 2")
    put(root, "nomess.json", json.dumps(dict(cfg, main_branch="main", review={"level": "extreme"})))
    expect(nm(root, "lessons", "status").returncode == 2, "review.level 非法应退出 2")
    put(root, "nomess.json", b"\xef\xbb\xbf" + json.dumps(dict(cfg, main_branch="main")).encode("utf-8"))
    expect(nm(root, "lessons", "status").returncode == 0, "BOM 配置应能读")
    # 无 nomess.json:退出 2,不悄悄建库
    bare = os.path.join(tmp, "bare")
    os.makedirs(bare)
    p = nm(bare, "lessons", "add", "x", "-s", "y", "-b", "z")
    expect(p.returncode == 2 and not os.path.exists(os.path.join(bare, "docs")), "无配置时 lessons add 应报错且不建目录")


def test_check_glob(tmp):
    # check.rules 的 glob / allow 用 pathglob:{a,b} 展开、*.py 任意层;不支持的 glob 报错
    rule = {"id": "G1", "level": "red", "what": "w", "why": "y", "glob": "src/{a,b}.py", "forbid": "BAD",
            }
    files = [("src/a.py", "BAD\n"), ("src/b.py", "BAD\n"), ("src/c.py", "BAD\n"), ("deep/x/y.py", "BAD\n")]
    root = mkrepo(tmp, "chkglob", {"check": {"rules": [rule, dict(rule, id="G2", glob="*.py")]},
                                   "allow": [{"rule": "G1", "file": "src/{b,z}.py", "reason": "r"}]}, files)
    p = nm(root, "check", "--red")
    out = p.stdout
    expect(p.returncode == 1 and "src/a.py" in out and "deep/x/y.py" in out, "check glob 应命中 src/a.py 和深层 *.py: %r" % out)
    g1 = [l for l in out.splitlines() if "G1" in l]
    expect(not any("src/b.py" in l or "src/c.py" in l for l in g1), "G1 不该报 allow 的 b.py 和不匹配的 c.py: %r" % g1)
    put(root, "nomess.json", json.dumps({"format": "nomess/1", "main_branch": "main", "lang": "zh-CN",
                                         "check": {"rules": [dict(rule, glob="!src/*.py")]}}))
    expect(nm(root, "check").returncode == 2, "不支持的 glob 应报配置错误退出 2")


def test_docgen_bytes(tmp):
    # CRLF 文件做 docgen:标记外字节不变,生成段沿用 CRLF;子进程中文输出
    root = mkrepo(tmp, "crlf", {"docgen": {"zh": {"file": "docs/t.md", "cmd": [sys.executable, "-c", "print('中文输出\\n第二行')"]}}})
    pre = "# 标题\r\n手写\r\n\r\n<!-- GEN:zh BEGIN -->\r\n"
    post = "<!-- GEN:zh END -->\r\n尾巴\r\n"
    path = put(root, "docs/t.md", (pre + "旧\r\n" + post).encode("utf-8"))
    nm(root, "docgen")
    data = open(path, "rb").read()
    expect(data.startswith(pre.encode("utf-8")) and data.endswith(post.encode("utf-8")), "CRLF 文件标记之外的字节被改了")
    mid = data[len(pre.encode("utf-8")):-len(post.encode("utf-8"))]
    expect(mid == "中文输出\r\n第二行\r\n".encode("utf-8"), "生成段内容或换行不对: %r" % mid)
    # 生成器非零退出:退出 2,不是 1
    put(root, "nomess.json", json.dumps({"format": "nomess/1", "main_branch": "main",
        "docgen": {"zh": {"file": "docs/t.md", "cmd": [sys.executable, "-c", "import sys; sys.exit(3)"]}}}))
    p = nm(root, "docgen")
    expect(p.returncode == 2 and "Traceback" not in p.stderr, "生成器失败应退出 2 且无 traceback")


def test_map_features(tmp):
    # 可选捕获组、热点、子系统、系统页三行头、依赖(六种语言)
    files = [
        ("src/a.py", '# 甲\nEVENT("save")\nOPT\n'),
        ("src/b.py", '# 乙\nEVENT("save")\nOPT(x)\n'),
        ("docs/systems/core.md", "# core\n这是什么：核心\n"),
    ]
    cfg = {"systems": {"core": ["src/*"]},
           "map": {"events": {"title": "事件", "columns": ["事件"], "glob": "src/*.py", "regex": 'EVENT\\("(\\w+)"\\)',
                              "file_col": True, "hotspot": {"by": "事件", "max": 1, "label": "同一事件多处发"}},
                   "opt": {"title": "可选", "columns": ["x"], "glob": "src/*.py", "regex": "OPT(?:\\((\\w)\\))?"}}}
    root = mkrepo(tmp, "mapf", cfg, files)
    p = nm(root, "map")
    expect(p.returncode == 0 and "Traceback" not in p.stderr, "可选捕获组不该崩")
    idx = read(root, "docs/system-map/index.md")
    expect(re.search(r"同一事件多处发:`save`", idx), "首页热点清单缺 save 一行")
    expect("core" in idx and "核心" in idx and "```mermaid" in idx, "首页缺子系统行或依赖图")
    p = nm(root, "check", "--all")
    expect("黄 DOC3 docs/systems/core.md" in p.stdout, "系统页缺三行头应报黄")
    put(root, "docs/systems/core.md", "# core\n这是什么：核心\n为什么要有：测试\n和谁配合：无\n")
    expect("DOC3" not in nm(root, "check", "--all").stdout, "补全三行头后不该再报")
    put(root, "docs/log.md", "# 记录\n见 [x](gone.md)\n```\n[y](nope.md)\n```\n")
    p = nm(root, "check", "--all")
    expect("红 DOC1 docs/log.md:2" in p.stdout and "nope" not in p.stdout and p.returncode == 1, "断链应报红(代码块里的不算)")

    # 依赖:Python、TS、C 各一条(验收要求),另验 Go / Rust / C#
    dfiles = [
        ("src/m.py", "# m\nimport util\n"), ("src/util.py", "# util\n"),
        ("web/a.ts", "// a\nimport { x } from './b'\n"), ("web/b.ts", "// b\n"),
        ("c/x.c", '// x\n#include "y.h"\n'), ("c/y.h", "// y\n"),
        ("go.mod", "module ex.com/app\n"), ("main.go", '// main\npackage main\nimport "ex.com/app/pkg"\n'), ("pkg/p.go", "// p\npackage pkg\n"),
        ("rs/src/main.rs", "// r\nmod util;\n"), ("rs/src/util.rs", "// u\n"),
        ("cs/A.cs", "// A\nusing App.Core;\n"), ("cs/B.cs", "// B\nnamespace App.Core {}\n"),
    ]
    root = mkrepo(tmp, "deps", {}, dfiles)
    nm(root, "map")
    d = read(root, "docs/system-map/deps.md")
    rows = [l for l in d.split("\n") if l.startswith("| ") and "---" not in l and not l.startswith("| 文件")]
    expect("(6 条" in d and len(rows) == 6, "deps.md 应出 6 条边(py/ts/c/go/rs/cs 各一),实际 %d" % len(rows))
    for edge in ("| src/m.py | src/util.py |", "| web/a.ts | web/b.ts |", "| c/x.c | c/y.h |", "| main.go | pkg/p.go |",
                 "| rs/src/main.rs | rs/src/util.rs |", "| cs/A.cs | cs/B.cs |"):
        expect(edge in d, "deps.md 缺 " + edge)


def test_lessons_index(tmp):
    root = mkrepo(tmp, "lidx", {"docgen": {"lessons": {"file": "docs/lessons/README.md", "builtin": "lessons-index"}}},
                  [("docs/lessons/README.md", "# 教训\n<!-- GEN:lessons BEGIN -->\n<!-- GEN:lessons END -->\n"),
                   ("docs/lessons/a.md", "# 主题甲\n## t\n概述: s\n内容: b\n")])
    nm(root, "docgen")
    expect("[主题甲](a.md) — 1 条" in read(root, "docs/lessons/README.md"), "lessons-index 不对")


def test_cmd_entry(tmp):
    if os.name != "nt":
        return
    root = os.path.join(tmp, "repo")
    cmd = os.path.join(PLUGIN, "bin", "nomess.cmd")
    p = subprocess.run(["cmd", "/c", cmd], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    expect(p.returncode == 2 and "usage: nomess" in p.stdout, "nomess.cmd 无参数应出用法行、退出 2: %r" % p.stdout)
    p = subprocess.run(["cmd", "/c", cmd, "lessons", "status"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    expect(p.returncode == 0 and "inbox" in p.stdout, "cmd /c nomess.cmd lessons status 应成功: %r %r" % (p.stdout, p.stderr))
    p = subprocess.run(["cmd", "/c", cmd, "check", "--red"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    expect(p.returncode == 1, "nomess.cmd 应透传退出码 1,实际 %d" % p.returncode)
    print("$ cmd /c bin\\nomess.cmd lessons status -> ok")


def test_review2(tmp):
    """第二轮审查补的用例:CRLF 正文 / 旧基线 / 非法正则 / map 表名 / 链接检查。"""
    # 12: py 生成器返回 CRLF 正文,写进 CRLF 文件不出 \r\r\n
    root = mkrepo(tmp, "r2crlf", {"docgen": {"g": {"file": "docs/t.md", "py": "gen.py:g"}}})
    put(root, "gen.py", "def g():\n    return 'a\\r\\nb\\r\\n'\n")
    path = put(root, "docs/t.md", b"x\r\n<!-- GEN:g BEGIN -->\r\nold\r\n<!-- GEN:g END -->\r\n")
    nm(root, "docgen")
    data = open(path, "rb").read()
    expect(data == b"x\r\n<!-- GEN:g BEGIN -->\r\na\r\nb\r\n<!-- GEN:g END -->\r\n", "CRLF 正文写出不对: %r" % data)
    # 6: 旧格式基线(字符串数组)明确报错退出 2,--freeze 重新冻结后恢复
    root = mkrepo(tmp, "r2base", {"check": {"rules": [{"id": "R1", "level": "red", "what": "w", "why": "y", "glob": "*.py", "forbid": "bad"}]}},
                  [("a.py", "bad\n")])
    put(root, ".nomess-baseline.json", '["R1|a.py|bad"]')
    p = nm(root, "check")
    expect(p.returncode == 2 and "nomess-baseline/2" in p.stderr and "Traceback" not in p.stderr, "旧基线应退出 2 并说明: %r" % p.stderr)
    os.remove(os.path.join(root, ".nomess-baseline.json"))
    expect(nm(root, "check", "--freeze").returncode == 0 and nm(root, "check").returncode == 0, "删掉旧基线重新冻结后应通过")
    # 8: 非法正则 = 运行故障退出 2,不是红项 1
    root2 = mkrepo(tmp, "r2rx", {"check": {"rules": [{"id": "R1", "level": "red", "what": "w", "why": "y", "glob": "*.py", "forbid": "["}]}},
                   [("a.py", "x\n")])
    p = nm(root2, "check", "--red")
    expect(p.returncode == 2 and "Traceback" not in p.stderr, "非法正则应退出 2 且无 traceback")
    # 5: map 表名不能越出生成目录 / 与内置页大小写冲突
    for bad in ("../../CLAUDE", "a/b", "Files", "a:b", "CON", "x."):
        r = mkrepo(tmp, "r2map" + str(abs(hash(bad))), {"map": {bad: {"title": "t", "columns": ["c"], "glob": "*.py", "regex": "(x)"}}},
                   [("a.py", "x\n")])
        p = nm(r, "map")
        expect(p.returncode == 2 and not os.path.exists(os.path.join(r, "CLAUDE.md")) and not os.path.exists(os.path.join(r, "docs", "system-map")),
               "非法表名应退出 2 且不写任何页: " + bad)
    # 7: 链接检查——URL 编码、尖括号、~~~ 围栏都不报;真断链仍报;记忆体检的 #锚点 不报
    root = mkrepo(tmp, "r2link", {}, [("docs/my file.md", "x\n"), ("docs/ok.md",
        "[a](my%20file.md) [b](<my file.md>) [c](my%20file.md#sec) [d](#top)\n~~~md\n[e](nope.md)\n~~~\n[f](missing.md)\n")])
    p = nm(root, "check", "--red", "--json")
    reds = json.loads(p.stdout)
    expect(len(reds) == 1 and "missing.md" in reds[0]["msg"], "链接检查只应报 missing.md: %r" % p.stdout)
    mem = os.path.join(tmp, "r2mem")
    put(mem, "MEMORY.md", "[t](topic.md#section)\n")
    put(mem, "topic.md", "## a\n")
    p = nm(root, "check", "--memory", mem)
    expect(p.returncode == 0, "记忆里的 (topic.md#section) 不应报断链")
    # 扩展依赖:status --json 带 lessons_dir;--json 时 py 生成器的 print 不进 stdout
    root = mkrepo(tmp, "r2json", {"lessons_dir": "kb/les", "docgen": {"g": {"file": "docs/t.md", "py": "gen.py:g"}}})
    put(root, "gen.py", "def g():\n    print('noise')\n    return 'new'\n")
    put(root, "docs/t.md", "<!-- GEN:g BEGIN -->\nold\n<!-- GEN:g END -->\n")
    p = nm(root, "status", "--json")
    try:
        st = json.loads(p.stdout)
    except ValueError:
        st = {}
    expect(st.get("lessons_dir") == "kb/les", "status --json 要带 lessons_dir: %r" % p.stdout)
    expect("noise" in p.stderr, "生成器的 print 应转到 stderr")
    p = nm(root, "check", "--json")
    expect(p.stdout.strip().startswith("[") and "noise" not in p.stdout, "check --json 的 stdout 只许有 JSON: %r" % p.stdout)


def test_dream(tmp):
    # P4:同标题覆盖、标题几乎相同和 inbox 结构的体检、记忆页标题重复
    root = mkrepo(tmp, "dream", {}, [("docs/lessons/core.md",
        "# 教训\n\n## 改存档字段前先查兼容\n概述: 旧\n内容: 旧做法\n第二行\n\n## 别的\n概述: x\n内容: y\n")])
    p = nm(root, "lessons", "add", "改存档字段前先查兼容 ", "-s", "新概述", "-b", "新做法")
    expect("已覆盖 core.md#" in p.stdout, "同标题 add 应输出已覆盖: %r" % p.stdout)
    nm(root, "lessons", "add", "改存档字段前 先查兼容", "-s", "再改", "-b", "第三版")
    core = read(root, "docs/lessons/core.md")
    expect(core.count("## 改存档字段前") == 1 and "第三版" in core and "旧做法" not in core and "第二行" not in core,
           "同标题 add 两次库里只该有一条: %r" % core)
    expect("更新: " in core and "## 别的" in core, "覆盖应写更新、不碰下一条: %r" % core)
    expect(not os.path.exists(os.path.join(root, "docs", "lessons", "inbox.md")), "覆盖时不该写 inbox")
    p = nm(root, "lessons", "add", "新条目", "-s", "s", "-b", "b")
    expect("已加入 inbox.md" in p.stdout and "更新: " in read(root, "docs/lessons/inbox.md"), "新标题应进 inbox 并带更新")
    put(root, "docs/lessons/old.md", "# 旧\n\n## 新条目呀\n概述: s\n内容: 多行\n第二行\n")
    out = nm(root, "check", "--all").stdout
    expect("黄 L4" in out and "新条目呀" in out, "标题几乎相同应报 L4: %r" % out)
    sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
    import lessons
    es = {e["title"]: e for e in lessons.parse(os.path.join(root, "docs", "lessons", "old.md"))}
    expect(es["新条目呀"]["body"] == "多行\n第二行", "内容应跨多行: %r" % es["新条目呀"]["body"])

    # 记忆:M7 本目录标题几乎相同
    mem = os.path.join(tmp, "projects", "proj-a", "memory")
    put(mem, "MEMORY.md", "- [PowerShell 改文件会乱码](ps.md) — 何时用\n- [PowerShell改文件会乱码!](ps2.md) — 何时用\n- [别的主题](other.md) — 何时用\n")
    for fn in ("ps.md", "ps2.md", "other.md"):
        put(mem, fn, "## a\n## b\n## c\n")
    out = nm(root, "check", "--memory", mem, "--all").stdout
    expect("黄 M7 ps.md" in out, "本目录标题几乎相同应报 M7: %r" % out)


def lesson(title, paths="", rule="", extra=""):
    """一条教训的文本;extra 是插在内容之前的额外键行(如 被取代)。"""
    return "## %s\n概述: 何时 x\n状态: 已核实\n%s%s%s内容: 细节\n\n" % (
        title, "路径: %s\n" % paths if paths else "", "规则: %s\n" % rule if rule else "", extra)


def rule_files(root):
    """{(paths...): 正文} :生成的规则文件按 frontmatter 的 paths 索引。"""
    sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
    import rules
    d = os.path.join(root, ".claude", "rules", "nomess")
    out = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        text = read(root, ".claude/rules/nomess/" + fn)
        out[tuple(rules.parse_frontmatter(text))] = text
    return out


def test_rules(tmp):
    # P7 + 第三轮审查:规则文件按条目自己的路径集合生成、frontmatter 校验、未核实 / 没写状态不出现、--check
    files = [("src/render/a.py", "# a\n"), ("src/net/b.py", "# b\n"), ("tools/t.py", "# t\n"),
             ("docs/lessons/core.md", "# 教训\n\n" + lesson("渲染前先清缓存", "src/render/**", "改渲染前先清缓存")
              + lesson("网络别阻塞", "src/net/*.py, tools/*.py", "网络调用一律异步")
              + lesson("没写规则", "src/net/**", "")
              + lesson("未核实的", "src/net/**", "未核实不生成").replace("已核实", "未核实")
              + lesson("没写状态", "src/net/**", "没状态不生成").replace("状态: 已核实\n", "")),
             ("docs/systems/render.md", "# render\n这是什么：渲染\n\n## 坑\n### 别在帧中改纹理\n路径: src/render/**\n规则: 帧中不要改纹理\n状态: 已核实\n内容: x\n\n## 别的\n")]
    root = mkrepo(tmp, "rules", {"systems": {"render": ["src/render/*"], "net": ["src/net/*"]}}, files)
    expect(nm(root, "rules").returncode == 0, "rules 应成功")
    rf = rule_files(root)
    expect(sorted(rf) == [("src/net/*.py", "tools/*.py"), ("src/render/**",)], "应按路径集合生成两份: %r" % list(rf))
    t = rf[("src/render/**",)]
    expect(t.startswith('---\npaths:\n  - "src/render/**"\n---\n') and t.count("---") == 2, "frontmatter 只该有条目自己的 paths: %r" % t)
    expect("- 改渲染前先清缓存 → docs/lessons/core.md#渲染前先清缓存" in t and "- 帧中不要改纹理 → docs/systems/render.md#别在帧中改纹理" in t,
           "同路径的条目应进同一份: %r" % t)
    allt = "".join(rf.values())
    expect("未核实不生成" not in allt and "没状态不生成" not in allt, "未核实、没写状态的不该出现")
    names = sorted(os.listdir(os.path.join(root, ".claude", "rules", "nomess")))
    expect(all(re.fullmatch(r"[0-9a-f]{8}\.md", n) for n in names), "文件名应是 8 位小写十六进制: %r" % names)
    expect(nm(root, "rules", "--check").returncode == 0, "没变化时 rules --check 应退出 0")
    out = nm(root, "check", "--all").stdout
    expect(not re.search(r"RUL[1-4]", out), "干净时不该有 RUL1-4: %r" % out)
    expect("黄 RUL5 docs/lessons/core.md" in out and "未核实的" in out and "没写状态" in out, "有路径规则但没核实应报 RUL5: %r" % out)
    nm(root, "rules")
    rpath = ".claude/rules/nomess/" + next(n for n in names if read(root, ".claude/rules/nomess/" + n) == t)
    expect(read(root, rpath) == t, "重复生成应一字不差")

    # 改坏 frontmatter -> 红;重新生成后恢复
    put(root, rpath, t.replace("paths:", "path:"))
    p = nm(root, "check", "--all")
    expect("红 RUL1 " + rpath in p.stdout and p.returncode == 1, "frontmatter 改坏应报红: %r" % p.stdout)
    expect("红 RUL1" in nm(root, "check", "--red").stdout, "--red 也该报 RUL1")
    expect(nm(root, "rules", "--check").returncode == 1, "改坏后 rules --check 应退出 1")
    nm(root, "rules")
    expect("RUL1" not in nm(root, "check", "--all").stdout, "重新生成后红项应消失")

    # 路径对应的目录删掉 -> 黄 RUL4;条目没写全 -> RUL5;规则文件过时 -> 黄 RUL2
    shutil.rmtree(os.path.join(root, "src", "net"))
    out = nm(root, "check", "--all").stdout
    expect("黄 RUL4 docs/lessons/core.md" in out and "src/net/*.py" in out, "目录删掉应报 RUL4: %r" % out)
    expect("黄 RUL5 docs/lessons/core.md" in out and "没写规则" in out, "只写路径没写规则应报 RUL5: %r" % out)
    put(root, "docs/lessons/core.md", read(root, "docs/lessons/core.md").replace("改渲染前先清缓存", "改渲染前先清一遍缓存"))
    expect("黄 RUL2 " + rpath in nm(root, "check", "--all").stdout, "条目改了规则文件应过时")

    # 超 400 token -> 黄 RUL3
    many = "".join(lesson("条 %d" % i, "src/render/**", "渲染" + "很长的做法" * 6 + str(i)) for i in range(30))
    put(root, "docs/lessons/many.md", "# 多\n\n" + many)
    nm(root, "rules")
    out = nm(root, "check", "--all").stdout
    expect("黄 RUL3 " + rpath in out, "超预算应报 RUL3: %r" % out)

    # 条目没了就清掉旧文件和空目录;旧版按子系统命名的文件当多余的清掉
    root2 = mkrepo(tmp, "rules2", {}, [("src/x.py", "# x\n"), ("docs/lessons/a.md", "# a\n\n" + lesson("X 的坑", "src/**", "别碰 X"))])
    put(root2, ".claude/rules/nomess/src.md", '---\npaths:\n  - "src/**"\n---\nold\n')
    nm(root2, "rules")
    expect(list(rule_files(root2)) == [("src/**",)] and not os.path.exists(os.path.join(root2, ".claude/rules/nomess/src.md")),
           "旧的子系统命名文件应被清掉")
    os.remove(os.path.join(root2, "docs", "lessons", "a.md"))
    nm(root2, "rules")
    expect(not os.path.exists(os.path.join(root2, ".claude", "rules", "nomess")), "没有条目时应清掉旧规则文件和空目录")


def test_review3(tmp):
    """第三轮审查:glob 语义、空 systems、范围不扩大、链接防护、代码围栏、日期别名、--red 查 L5、目录名带方括号、--no-exec、记忆目录定位。"""
    sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
    import pathglob
    # 9 glob 对齐 Claude Code 官方说明
    for g, path, want in (("*.py", "src/a.py", True), ("*.py", "a.py", True), ("/src/**", "src/a.py", True), ("/src/**", "x/src/a.py", False),
                          ("/*.md", "a.md", True), ("/*.md", "d/a.md", False), ("src/[ab].py", "src/a.py", True), ("src/[!ab].py", "src/a.py", False),
                          ("src/*.py", "src/x/a.py", False), ("src/**/*.py", "src/a.py", True), ("src/**/*.py", "src/x/y/a.py", True),
                          ("src/*.{ts,tsx}", "src/a.tsx", True), ("{a,b}/{c,d}/*.ts", "b/d/x.ts", True), ("photos \\[2024/**", "photos [2024/a", True)):
        expect(bool(pathglob.compile(g).match(path)) == want, "glob %s 对 %s 应为 %s" % (g, path, want))
    for g in ("!x", "src/", "photos [2024/**", "{a", "x{y}"):
        try:
            pathglob.compile(g)
            expect(False, "不支持的 glob 应拒绝: " + g)
        except ValueError:
            pass
    root = mkrepo(tmp, "r3glob", {}, [("src/a.py", "# a\n"), ("docs/lessons/a.md", "# a\n\n" + lesson("任意层", "*.py", "py 规则")
                                       + lesson("根下", "/src/**", "根规则") + lesson("字符组", "src/[ab].py", "组规则")
                                       + lesson("坏的", "photos [2024/**", "坏规则"))])
    out = nm(root, "check", "--all").stdout
    expect("RUL4" not in out, "合法的无斜杠、根路径、字符组模式不该报 RUL4: %r" % out)
    expect("黄 RUL5 docs/lessons/a.md" in out and "坏的" in out, "不支持的 glob 应报 RUL5: %r" % out)
    nm(root, "rules")
    expect("坏规则" not in "".join(rule_files(root).values()) and len(rule_files(root)) == 3, "不支持的 glob 不生成")
    # 子系统归属用同一份匹配:* 不跨目录
    import map as nm_map
    of = nm_map.owners_of({"top": ["src/*"], "deep": ["src/*/**"]}, ["src/a.py", "src/x/a.py"])
    expect(of == {"src/a.py": "top", "src/x/a.py": "deep"}, "子系统 glob 的 * 不该跨目录: %r" % of)

    # 5 空的子系统路径列表拒绝
    p = nm(mkrepo(tmp, "r3empty", {"systems": {"src": []}}, [("src/a.py", "# a\n")]), "rules")
    expect(p.returncode == 2 and "systems.src" in p.stderr, "空的 systems 列表应退出 2: %r" % p.stderr)

    # 8 范围不扩大:同一子系统里客户端 / 服务器的规则各进各的
    root = mkrepo(tmp, "r3scope", {"systems": {"src": ["src/**"]}}, [("src/client/a.py", "# a\n"), ("src/server/b.py", "# b\n"),
        ("docs/lessons/a.md", "# a\n\n" + lesson("客户端", "src/client/**", "只调远程接口") + lesson("服务器", "src/server/**", "直接访问数据库"))])
    nm(root, "rules")
    rf = rule_files(root)
    expect("直接访问数据库" not in rf.get(("src/client/**",), "x") and "只调远程接口" not in rf.get(("src/server/**",), "x")
           and len(rf) == 2, "客户端和服务器的规则不该混进一份: %r" % rf)

    # 4 输出目录是链接:拒绝写(没权限建链接的平台跳过)
    root = mkrepo(tmp, "r3link", {}, [("src/a.py", "# a\n"), ("docs/lessons/a.md", "# a\n\n" + lesson("X", "src/**", "别碰 X"))])
    shared = os.path.join(tmp, "r3shared")
    os.makedirs(shared)
    os.makedirs(os.path.join(root, ".claude", "rules"))
    try:
        os.symlink(shared, os.path.join(root, ".claude", "rules", "nomess"), target_is_directory=True)
        linked = True
    except (OSError, NotImplementedError):
        linked = os.name == "nt" and subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(root, ".claude", "rules", "nomess"), shared],
                                                    capture_output=True).returncode == 0
    if linked:
        p = nm(root, "rules")
        expect(p.returncode == 2 and not os.listdir(shared), "规则目录是链接时应拒绝写入: %r %r" % (p.stderr, os.listdir(shared)))

    # 11 代码围栏里的标题和键不是条目;同标题覆盖到条目真正的末尾
    fence = "## 真条目\n概述: a\n状态: 已核实\n内容: 例子\n```md\n## 假标题\n路径: src/**\n规则: 假规则\n```\n结尾行\n\n## 下一条\n概述: b\n内容: c\n"
    root = mkrepo(tmp, "r3fence", {}, [("src/a.py", "# a\n"), ("docs/lessons/a.md", "# a\n\n" + fence)])
    import lessons
    es = lessons.parse(os.path.join(root, "docs", "lessons", "a.md"))
    expect([e["title"] for e in es] == ["真条目", "下一条"] and "## 假标题" in es[0]["body"] and not es[0]["paths"], "围栏里的不该拆成条目: %r" % es)
    nm(root, "rules")
    expect(not rule_files(root), "围栏里的假规则不该生成")
    nm(root, "lessons", "add", "真条目", "-s", "新", "-b", "新内容")
    text = read(root, "docs/lessons/a.md")
    expect("假标题" not in text and "结尾行" not in text and "## 下一条" in text and "新内容" in text, "覆盖应到条目末尾、不留碎片: %r" % text)

    # 12 旧版的 日期: 读作 更新
    put(root, "docs/lessons/inbox.md", "# inbox\n\n## 老条目\n概述: x\n状态: 已核实\n日期: 2020-01-01\n内容: y\n")
    expect(lessons.parse(os.path.join(root, "docs", "lessons", "inbox.md"))[0]["updated"] == "2020-01-01", "日期: 应读作更新")
    expect("最早 " in nm(root, "lessons", "status").stdout and "最早 0 天" not in nm(root, "lessons", "status").stdout, "旧日期应算进最早天数")

    # 10 --red(提交钩子)也报 L5(inbox 标题重复),不报黄的 L4
    root = mkrepo(tmp, "r3l5", {}, [("docs/lessons/inbox.md", "# inbox\n\n## 甲\n概述: x\n内容: y\n\n## 甲 \n概述: x\n内容: y\n")])
    p = nm(root, "check", "--red")
    expect(p.returncode == 1 and "红 L5" in p.stdout and "L4" not in p.stdout, "--red 应报 L5: %r" % p.stdout)

    # 13 项目路径里有方括号:教训和规则照样扫到
    root = mkrepo(tmp, "r3[演示]", {}, [("src/a.py", "# a\n"), ("docs/lessons/a.md", "# a\n\n" + lesson("X", "src/**", "别碰 X"))])
    nm(root, "rules")
    expect(len(rule_files(root)) == 1 and nm(root, "rules", "--check").returncode == 0, "带方括号的路径应能扫到教训")

    # 1 --no-exec:不跑 cmd 规则和 cmd / py 生成器
    mark = os.path.join(tmp, "r3ran")
    touch = ["python", "-c", "open(%r, 'w').write('x')" % mark]
    root = mkrepo(tmp, "r3noexec", {"docgen": {"s": {"file": "d.md", "cmd": touch}, "p": {"file": "d.md", "py": "g.py:g"}},
                                   "check": {"rules": [{"id": "C1", "level": "red", "what": "w", "why": "y", "cmd": touch}]}},
                  [("d.md", "<!-- GEN:s BEGIN -->\n<!-- GEN:s END -->\n<!-- GEN:p BEGIN -->\n<!-- GEN:p END -->\n"),
                   ("g.py", "def g():\n    open(%r, 'w').write('x')\n    return 'y'\n" % mark)])
    p = nm(root, "check", "--all", "--no-exec")
    p2 = nm(root, "status", "--json", "--no-exec")
    expect(p.returncode == 0 and p2.returncode == 0 and not os.path.exists(mark), "--no-exec 不该执行项目代码: %r" % p.stdout)
    nm(root, "check", "--all")
    expect(os.path.exists(mark), "不加 --no-exec 时照常执行(证明上面的测试有效)")

    # 14 记忆目录:CLAUDE_CONFIG_DIR + 精确的仓库路径;找不到就为空并说原因,不往上级猜;autoMemoryDirectory 优先
    cfgdir = os.path.join(tmp, "r3claude")
    root = mkrepo(tmp, "r3mem", {})
    sub = os.path.join(root, "sub")
    os.makedirs(sub)
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(root))
    env = {"CLAUDE_CONFIG_DIR": cfgdir}
    s = json.loads(nm(root, "status", "--json", env=env).stdout)
    expect(s["memory_dir"] == "" and "not found" in s["memory_problem"], "没有记忆目录时应为空并说原因: %r" % s)
    os.makedirs(os.path.join(cfgdir, "projects", os.path.basename(os.path.dirname(root)) + "-up", "memory"))
    os.makedirs(os.path.join(cfgdir, "projects", slug, "memory"))
    s = json.loads(nm(root, "status", "--json", env=env).stdout)
    expect(s["memory_dir"].lower() == os.path.join(cfgdir, "projects", slug, "memory").replace("\\", "/").lower(), "应按仓库路径定位: %r" % s)
    custom = os.path.join(tmp, "r3custom")
    os.makedirs(custom)
    put(root, ".claude/settings.json", json.dumps({"autoMemoryDirectory": custom}))
    s = json.loads(nm(root, "status", "--json", env=env).stdout)
    expect(s["memory_dir"].lower() == custom.replace("\\", "/").lower() and "autoMemoryDirectory" in s["memory_source"], "autoMemoryDirectory 优先: %r" % s)



def test_map_budget(tmp):
    # P7:首页预算,固定裁法,两次生成一字不差;没填 systems 按顶层目录划
    ev = 'EVENT("%s")\n'
    files = [("alpha/f1.py", "# f\nimport beta.f1\n" + ev % "a1"), ("beta/f1.py", "# f\n" + ev % "b1"), ("gamma/f1.py", "# f\n" + ev % "g1")]
    spec = {"title": "事件", "columns": ["事件"], "glob": "**/*.py", "regex": 'EVENT\\("(\\w+)"\\)', "file_col": True,
            "hotspot": {"by": "事件", "max": 1, "label": "同一事件多处发"}}
    root = mkrepo(tmp, "budget", {"map": {"events": spec}}, files)
    nm(root, "map")
    idx = read(root, "docs/system-map/index.md")
    expect("**alpha**" in idx and '["gamma"]' in idx and "```mermaid" in idx, "没填 systems 应按顶层目录划,预算内画全部节点: %r" % idx)
    cfg = json.loads(read(root, "nomess.json"))
    cfg["map"]["index_tokens"] = 1
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    nm(root, "map")
    cut = read(root, "docs/system-map/index.md")
    expect('["gamma"]' not in cut and '["alpha"]' in cut and '["beta"]' in cut, "超预算先收子系统图:无边的节点去掉、有边的留下: %r" % cut)

    # 热点 12 条:预算内全列,超预算只留最重的 10 条加"其余 N 条见分页"
    many = [("alpha/h%d.py" % i, "# h\n" + ev % ("ev%d" % i)) for i in range(12)] + [("beta/h%d.py" % i, "# h\n" + ev % ("ev%d" % i)) for i in range(12)]
    root = mkrepo(tmp, "budget2", {"map": {"events": spec}}, many)
    nm(root, "map")
    expect(read(root, "docs/system-map/index.md").count("同一事件多处发") == 12, "预算内应列全部 12 条热点")
    cfg = json.loads(read(root, "nomess.json"))
    cfg["map"]["index_tokens"] = 1
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    nm(root, "map")
    first = read(root, "docs/system-map/index.md")
    expect(first.count("同一事件多处发") == 10 and "其余 2 条见分页" in first, "超预算热点应只留 10 条并写其余 2 条: %r" % first)
    nm(root, "map")
    expect(read(root, "docs/system-map/index.md") == first and nm(root, "map", "--check").returncode == 0, "两次生成应一字不差")
    expect("黄 MAP1 docs/system-map/index.md" in nm(root, "check", "--all").stdout, "裁完仍超预算应报 MAP1")
    cfg["map"]["index_tokens"] = "x"
    put(root, "nomess.json", json.dumps(cfg))
    expect(nm(root, "map").returncode == 2, "index_tokens 非正整数应退出 2")


def test_agents_entry(tmp):
    # P7:agents-entry 生成段(空仓库不超 12 行;大项目多两行)、AGENTS.md / CLAUDE.md 检查、方案头
    gen = {"docgen": {"agents": {"file": "AGENTS.md", "builtin": "agents-entry"}}}
    root = mkrepo(tmp, "agents", gen, [("AGENTS.md", "# 项目\n\n<!-- GEN:agents BEGIN -->\n<!-- GEN:agents END -->\n")])
    nm(root, "docgen")
    a = read(root, "AGENTS.md")
    body = a.split("<!-- GEN:agents BEGIN -->")[1].split("<!-- GEN:agents END -->")[0].strip().split("\n")
    expect(len(body) <= 12 and "nomess lessons find" in a and "schedule.md" not in a, "小项目 agents-entry 不超 12 行且没有会话协议: %r" % a)
    put(root, "docs/schedule.md", "# 排期\n")
    nm(root, "docgen")
    a = read(root, "AGENTS.md")
    body = a.split("<!-- GEN:agents BEGIN -->")[1].split("<!-- GEN:agents END -->")[0].strip().split("\n")
    expect("docs/schedule.md" in a and "log.md" not in a and len(body) <= 12, "大项目多一行会话协议(没有 log)")
    expect(nm(root, "docgen", "--check").returncode == 0, "生成后 --check 应通过")
    put(root, "CLAUDE.md", "# 规矩\n")
    expect("黄 AGENTS2 CLAUDE.md" in nm(root, "check", "--all").stdout, "CLAUDE.md 没导入应报黄")
    put(root, "CLAUDE.md", "@AGENTS.md\n# 规矩\n")
    expect("AGENTS2" not in nm(root, "check", "--all").stdout, "导入后不该再报")
    put(root, "AGENTS.md", read(root, "AGENTS.md") + "字" * 1600)
    expect("黄 AGENTS1 AGENTS.md" in nm(root, "check", "--all").stdout, "AGENTS.md 超预算应报黄")
    put(root, "docs/plans/new.md", "状态: 提案\n日期: 2026-01-01\n取代: archive/gone.md\n")
    put(root, "docs/plans/archive/2026-01-01-old.md", "# 旧\n日期: 2026-01-01\n")
    put(root, "docs/plans/archive/2026-01-02-b.md", "状态: 已采纳\n被取代: 2026-01-01-old.md\n")
    out = nm(root, "check", "--all").stdout
    expect("红 PLN1 docs/plans/new.md" in out and "gone.md" in out, "取代指向不存在的文件应报红: %r" % out)
    expect("黄 PLN2 docs/plans/archive/2026-01-01-old.md" in out, "归档方案缺状态应报黄")
    expect("黄 PLN2 docs/plans/archive/2026-01-02-b.md" in out and "PLN1 docs/plans/archive" not in out,
           "写了被取代而状态不对应报黄,且指向存在的文件不报红")


def test_readme():
    text = open(os.path.join(PLUGIN, "scripts", "README.md"), encoding="utf-8").read()
    blocks = re.findall(r"```json\n(.*?)```", text, re.S)
    expect(blocks, "README 里没有 json 代码块")
    for b in blocks:
        try:
            json.loads(b)
        except ValueError as e:
            expect(False, "README 的 JSON 代码块不合法: %s" % e)


YAML_PLAIN_BAD_START = tuple("[]{}&*!|>'\"%@,#`")


def frontmatter_errors(text):
    """只针对 skill / 子代理定义 frontmatter 的最小 YAML 校验(标准库没有 YAML 解析器):
    每行是顶层 `key: value` 或块标量的缩进续行;普通标量不得含 `: `、` #`,不得以 YAML 指示符开头;引号要成对。"""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return ["没有 --- 包起来的 frontmatter"]
    errs, block, keys = [], False, set()
    for line in lines[1:lines.index("---", 1)]:
        if block and line.startswith("  ") and line.strip():
            continue
        block = False
        m = re.match(r"^([a-z][a-z0-9-]*): ?(.*)$", line)
        if not m:
            errs.append("不是 key: value: %r" % line)
            continue
        key, v = m.groups()
        keys.add(key)
        if v in (">-", ">", "|", "|-"):
            block = True
        elif v[:1] in ("'", '"'):
            if len(v) < 2 or v[-1] != v[0]:
                errs.append("%s 的引号不成对" % key)
        elif v.startswith(YAML_PLAIN_BAD_START) or ": " in v or " #" in v or v.endswith(":"):
            errs.append("%s 的普通标量要加引号或改 >-: %r" % (key, v))
    if not {"name", "description"} <= keys:
        errs.append("缺 name 或 description")
    return errs


def test_frontmatter():
    root = os.path.dirname(PLUGIN)
    paths = []
    for base in (PLUGIN, os.path.join(root, "docs", "zh-CN")):
        for sub, pat in (("skills", "SKILL.md"), ("agents", None)):
            d = os.path.join(base, sub)
            for name in sorted(os.listdir(d)):
                paths.append(os.path.join(d, name, pat) if pat else os.path.join(d, name))
    expect(len(paths) == 16, "英文 + 中文应各 6 个 skill + 2 个子代理: %d" % len(paths))
    for p in paths:
        for e in frontmatter_errors(open(p, encoding="utf-8").read()):
            expect(False, "%s: %s" % (os.path.relpath(p, root), e))
    expect(frontmatter_errors("---\nname: x\ndescription: a: b\n---\n"), "校验器应抓出未加引号的冒号")


GOLDEN = os.path.join(HERE, "golden.json")
LANG_WORDS = {  # 同一份内容,两种语言的固定字段名和状态词
    "en": dict(sys=("What", "Why", "Works with"), lesson=("When", "What", "Status", "Paths", "Rule"), ok="verified",
               plan=("Status", "Supersedes", "Superseded-by"), plan_st=("accepted", "superseded"),
               sched=("Package", "Depends", "Status"), st=("Merged", "Doing", "Todo")),
    "zh-CN": dict(sys=("这是什么", "为什么要有", "和谁配合"), lesson=("概述", "内容", "状态", "路径", "规则"), ok="已核实",
                  plan=("状态", "取代", "被取代"), plan_st=("已采纳", "已被取代"),
                  sched=("包", "依赖", "状态"), st=("已合", "在做", "待派")),
}


def golden_repo(tmp, lang):
    """一个确定性的假仓库(内容全由测试写成 LF),覆盖 docgen / map / rules / 教训 / 方案头 / 总排期,固定字段名按 lang 写。"""
    w = LANG_WORDS[lang]
    sysw, les = w["sys"], w["lesson"]
    root = mkrepo(tmp, "golden-" + lang, {
        "lang": lang, "systems": {"core": ["src/core/*"], "net": ["src/net/*"]},
        "docgen": {"modules": {"file": "docs/design.md", "map": "modules"},
                   "entry": {"file": "docs/design.md", "builtin": "agents-entry"}},
        "map": {"modules": {"title": "Modules", "columns": ["name", "n"], "glob": "src/*/*.py", "regex": "REGISTER\\(\"(\\w+)\", (\\d+)\\)",
                            "file_col": True, "misses": "dynamic names", "hotspot": {"by": "name", "max": 1, "label": "registered twice"}}}},
        [("src/core/a.py", '# Core entry.\nREGISTER("alpha", 1)\n'),
         ("src/net/b.py", '# Network layer.\nREGISTER("beta", 2)\nREGISTER("alpha", 3)\n'),
         ("docs/design.md", "# Design\n\n" + "".join("<!-- GEN:%s BEGIN -->\n<!-- GEN:%s END -->\n\n" % (n, n) for n in ("modules", "entry"))),
         ("docs/systems/core.md", "# core\n%s: the core\n%s: because\n%s: net\n" % sysw),
         ("docs/systems/net.md", "# net\n%s: the network\n%s: because\n%s: core\n\n## Pitfalls\n\n### Never block\n%s: x\n%s: y\n%s: %s\n"
          "%s: src/net/**\n%s: Never block the IO thread\n" % (sysw + (les[0], les[1], les[2], w["ok"], les[3], les[4]))),
         ("docs/lessons/core.md", "# Lessons\n\n## Check compat first\n%s: touching src/core save format\n%s: read the old version\n%s: %s\n"
          % (les[0], les[1], les[2], w["ok"])),
         ("docs/plans/archive/old.md", "%s: %s\n%s: ../new.md\n\n# Old\n" % (w["plan"][0], w["plan_st"][1], w["plan"][2])),
         ("docs/plans/new.md", "%s: %s\n%s: archive/old.md\n\n# New\n" % (w["plan"][0], w["plan_st"][0], w["plan"][1])),
         ("docs/schedule.md", "| %s | %s | %s |\n|---|---|---|\n| P1 | | %s |\n| P2 | P1 | %s |\n| P3 | P2 | %s |\n" % (w["sched"] + w["st"]))])
    return root


def manifest(root):
    out = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", ".nomess")]  # .nomess 是本机缓存,不进版本库
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                data = fh.read()
            rel = os.path.relpath(p, root).replace("\\", "/")
            expect(b"\r" not in data, "生成物 / 测试文件里不该有 CR: " + rel)
            out[rel] = hashlib.sha256(data).hexdigest()
    return dict(sorted(out.items()))


def test_golden(tmp, write):
    """跨平台逐字节相同:同一个假仓库生成的全部文件的哈希要和 tests/golden.json 一致;各平台的 CI 都跑这一份。"""
    gold = {}
    for lang in ("en", "zh-CN"):
        root = golden_repo(tmp, lang)
        for cmd in (("docgen",), ("map",), ("rules",)):
            expect(nm(root, *cmd).returncode == 0, "%s 生成失败: %s" % (lang, cmd))
        p = nm(root, "check", "--all")
        expect(p.returncode == 0 and not any(k in p.stdout for k in ("DOC3", "PLN", "GEN", "DOC2")),
               "%s 假仓库不该有红项、说明页头、方案头、过时项: %r" % (lang, p.stdout))
        expect(nm(root, "docgen", "--check").returncode == 0 and nm(root, "map", "--check").returncode == 0, lang + " 生成后应不过时")
        gold[lang] = manifest(root)
        expect(len([f for f in gold[lang] if f.startswith(".claude/rules/nomess/")]) == 1, "%s 应只生成 net 的规则文件" % lang)
    if write:
        with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
            json.dump(gold, f, indent=1, sort_keys=True)
            f.write("\n")
        print("golden.json 已重写")
        return
    with open(GOLDEN, encoding="utf-8") as f:
        want = json.load(f)
    for lang in gold:
        diff = sorted(k for k in set(gold[lang]) | set(want.get(lang, {})) if gold[lang].get(k) != want.get(lang, {}).get(k))
        expect(not diff, "%s 生成物和 golden.json 不一致: %s(有意改了就跑 python tests/run.py --write-golden)" % (lang, diff))


def fail_lines(p):
    return [l for l in p.stdout.splitlines() if l.startswith(("FAIL", "失败"))]


def test_lang(tmp):
    """lang 切换:提示语换语言、规则号不变;中英文键写的同一条教训解析结果相同;lessons add 按 lang 写键;doctor 三种坏情况各报一行。"""
    rule = {"check": {"rules": [{"id": "R1", "level": "red", "what": "no print", "why": "debug output", "glob": "src/*.py", "forbid": "print\\("}]}}
    outs = {}
    for lang in ("en", "zh-CN"):
        root = mkrepo(tmp, "lang-" + lang, dict(rule, lang=lang), [("src/a.py", "# h\nprint(1)\n")])
        p = nm(root, "check", "--all")
        outs[lang] = p.stdout
        expect(p.returncode == 1, lang + " 违规应退出 1")
        j = json.loads(nm(root, "check", "--json").stdout)
        expect([(x["rule"], x["file"], x["line"]) for x in j] == [("R1", "src/a.py", 2)], lang + " --json 规则号和位置: %r" % j)
    expect(outs["en"].startswith("red R1 src/a.py:2 prevents: debug output") and "red 1 yellow 0" in outs["en"], "en 输出: %r" % outs["en"])
    expect(outs["zh-CN"].startswith("红 R1 src/a.py:2 防:debug output") and "红 1 黄 0" in outs["zh-CN"], "zh 输出: %r" % outs["zh-CN"])
    p = nm(mkrepo(tmp, "lang-bad", {"lang": "fr"}), "check")
    expect(p.returncode == 2 and "lang" in p.stderr, "不认识的 lang 应退出 2: %r" % p.stderr)
    # 中英文键同一条教训解析相同
    sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
    import lessons
    d = os.path.join(tmp, "les")
    en = "## Same\nWhen: a path.py\nStatus: unverified\nUpdated: 2026-01-01\nPaths: src/**\nRule: do it\nWhat: line1\nline2\n"
    zh = "## Same\n概述: a path.py\n状态: 未核实\n更新: 2026-01-01\n路径: src/**\n规则: do it\n内容: line1\nline2\n"
    put(d, "en.md", en)
    put(d, "zh.md", zh)
    a, b = lessons.parse(os.path.join(d, "en.md"))[0], lessons.parse(os.path.join(d, "zh.md"))[0]
    for e in (a, b):
        e.pop("file")
    expect(a == b and a["status"] == "unverified" and not a["verified"] and a["body"] == "line1\nline2", "中英键解析应相同: %r %r" % (a, b))
    expect(lessons.count_unverified(d) == 2, "中英写法的未核实都要数到")
    # add 按 lang 写键和状态词
    root = os.path.join(tmp, "lang-en")
    nm(root, "lessons", "add", "T", "-s", "s", "-b", "b", "--unverified")
    inbox = read(root, "docs/lessons/inbox.md")
    expect("When: s" in inbox and "What: b" in inbox and "Status: unverified" in inbox and "概述" not in inbox, "en 的 add 应写英文键: %r" % inbox)
    nm(root, "lessons", "add", "T", "-s", "s2", "-b", "b2")
    expect("Status: verified" in read(root, "docs/lessons/inbox.md"), "覆盖后状态应是 verified")
    # doctor:缺 Python / 缺 nomess.json / CLAUDE.md 没导入,各报一行
    py = sys.executable
    good = mkrepo(tmp, "doc-good", {"lang": "en"}, [("AGENTS.md", "# a\n"), ("CLAUDE.md", "@AGENTS.md\n")])
    p = nm(good, "doctor", "--python", py)
    expect(p.returncode == 0 and not fail_lines(p), "doctor 全好应退出 0: %r" % p.stdout)
    p = nm(good, "doctor", "--python", "no-such-python-xyz")
    fl = fail_lines(p)
    expect(p.returncode == 1 and len(fl) == 1 and "no-such-python-xyz" in fl[0] and "Fix:" in fl[0], "缺 Python 应报一行: %r" % p.stdout)
    empty = os.path.join(tmp, "doc-empty")
    os.makedirs(empty)
    p = nm(empty, "doctor", "--python", py)
    fl = fail_lines(p)
    expect(p.returncode == 1 and len(fl) == 1 and "nomess.json" in fl[0] and "/nomess:init" in fl[0], "缺 nomess.json 应报一行: %r" % p.stdout)
    noimp = mkrepo(tmp, "doc-noimport", {"lang": "en"}, [("AGENTS.md", "# a\n"), ("CLAUDE.md", "# c\n")])
    p = nm(noimp, "doctor", "--python", py)
    fl = fail_lines(p)
    expect(p.returncode == 1 and len(fl) == 1 and "@AGENTS.md" in fl[0], "CLAUDE.md 没导入应报一行: %r" % p.stdout)
    zhdoc = mkrepo(tmp, "doc-zh", {"lang": "zh-CN"}, [("AGENTS.md", "# a\n"), ("CLAUDE.md", "# c\n")])
    p = nm(zhdoc, "doctor", "--python", py)
    expect(len([l for l in fail_lines(p) if l.startswith("失败")]) == 1 and "修法" in p.stdout, "zh 的 doctor 应报中文: %r" % p.stdout)


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-test-")
    try:
        test_fixture(tmp)
        test_config(tmp)
        test_check_glob(tmp)
        test_docgen_bytes(tmp)
        test_map_features(tmp)
        test_lessons_index(tmp)
        test_cmd_entry(tmp)
        test_review2(tmp)
        test_dream(tmp)
        test_rules(tmp)
        test_review3(tmp)
        test_map_budget(tmp)
        test_agents_entry(tmp)
        test_readme()
        test_frontmatter()
        test_lang(tmp)
        test_golden(tmp, "--write-golden" in sys.argv)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name in sorted(os.listdir(HERE)):  # 各包的用例文件:各自是独立脚本,失败退出非 0
        if name.startswith("test_") and name.endswith(".py"):
            print("== " + name)
            p = subprocess.run([sys.executable, os.path.join(HERE, name)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("   " + (p.stdout.strip().splitlines() or ["(no output)"])[-1])
            if p.returncode:
                fails.append("%s 失败(单独跑看详情)" % name)
    print("OK" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
