"""R2 文档类型的测试:新增放错位置的文件挡提交(红)而存量只黄、登记 doc_types 后放行、docs-index 两次生成逐字节相同、
配置写错退出 2、孤儿页、L6 和新增 doc_types 进必审项。全过打印 OK,否则列出失败项并退出码 1。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo, nm, put, read  # noqa: E402

RED, YELLOW = ("red", "红"), ("yellow", "黄")
INDEX_OVERVIEW = "# 总览\n\n链接 [系统](systems/core.md)\n\n<!-- GEN:docs-index BEGIN -->\n<!-- GEN:docs-index END -->\n"
GEN = {"docgen": {"docs-index": {"file": "docs/overview.md", "builtin": "docs-index"}}}


def git(root, *a):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p.stdout.strip()


def commit(root):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "c")
    return git(root, "rev-parse", "HEAD")


def doc4(root, base):
    p = nm(root, "check", "--ci", "--base", base, "--json")
    return p, [i for i in json.loads(p.stdout) if i["rule"] == "DOC4"]


def t_misplaced_new_red_old_yellow(tmp):
    root = mkrepo(tmp, "dt1", {}, [("docs/old/stray.md", "# 存量\n"), ("docs/systems/core.md", "# core\n")])
    base = commit(root)
    put(root, "docs/notes/new.md", "# 新\n")
    put(root, "docs/a/b/c.md", "# 三层\n")
    commit(root)
    p, f = doc4(root, base)
    by = {i["file"]: i["level"] for i in f}
    expect(by.get("docs/notes/new.md") in RED and by.get("docs/a/b/c.md") in RED, "新增的放错位置文件应红: %r" % by)
    expect(by.get("docs/old/stray.md") in YELLOW, "存量放错位置应黄: %r" % by)
    expect(p.returncode == 1, "有新红项应退出 1")
    expect("doc_types" in " ".join(i["msg"] for i in f) and "docs/" in " ".join(i["msg"] for i in f), "提示应带出路")
    put(root, "docs/systems/ok.md", "# ok\n")  # 合法位置不报
    commit(root)
    expect("docs/systems/ok.md" not in {i["file"] for i in doc4(root, base)[1]}, "类型位置里的页不该报")


def t_register_allows(tmp):
    root = mkrepo(tmp, "dt2", {}, [("docs/systems/core.md", "# core\n")])
    base = commit(root)
    put(root, "docs/api/x.md", "# api\n")
    cfg = json.loads(read(root, "nomess.json"))
    cfg["doc_types"] = [{"name": "api", "dir": "docs/api", "what": "对外接口参考"}]
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    commit(root)
    p, f = doc4(root, base)
    expect(not f, "登记 doc_types 后 docs/api/x.md 应放行: %r" % f)


def t_doc7_stale_page(tmp):
    """DOC7:改了子系统源文件、说明页没改 -> 钩子 / --ci 报黄;全量检查(--all)不报;说明页一起改了也不报。"""
    root = mkrepo(tmp, "dt7", {"systems": {"core": ["src/core/**"]}},
                  [("docs/systems/core.md", "# core\n"), ("src/core/a.py", "x = 1\n")])
    base = commit(root)
    put(root, "src/core/a.py", "x = 2\n")
    commit(root)
    f = [i for i in json.loads(nm(root, "check", "--ci", "--base", base, "--json").stdout) if i["rule"] == "DOC7"]
    expect([(i["file"], i["level"]) for i in f] == [("docs/systems/core.md", "yellow")], "改源文件没改说明页应报一条黄 DOC7: %r" % f)
    expect(not [i for i in json.loads(nm(root, "check", "--all", "--json").stdout) if i["rule"] == "DOC7"], "--all 不报 DOC7")
    base = commit(root)
    put(root, "src/core/a.py", "x = 3\n")
    put(root, "docs/systems/core.md", "# core\n\n改了\n")
    commit(root)
    f = [i for i in json.loads(nm(root, "check", "--ci", "--base", base, "--json").stdout) if i["rule"] == "DOC7"]
    expect(not f, "说明页一起改了不报: %r" % f)


def t_old_defaults(tmp):
    """老项目不写新键:docs_root 仍是 docs、教训库仍是 docs/lessons、对外 / 开发者文档只认仓库根的内置几个(DOC4 的结果由上面两条照旧验)。"""
    import doctypes
    import nm_config
    exp = nm_config.expanded({"format": "nomess/1", "main_branch": "main"})
    expect(exp["docs_root"] == "docs" and exp["lessons_dir"] == "docs/lessons", "缺省根和教训库目录不变: %r" % ((exp["docs_root"], exp["lessons_dir"]),))
    tier = doctypes.tier_of(exp)
    expect(tier("README.md") == "public" and tier("pkg/README.md") is None and tier("CONTRIBUTING.md") == "dev" and tier("docs/x.md") is None,
           "内置三档只认仓库根")
    for extra in ({"public_docs": ["docs/**"]}, {"lessons_dir": "site/lessons", "public_docs": ["site/**"]}):
        try:
            nm_config.parse(json.dumps(dict({"format": "nomess/1", "main_branch": "main"}, **extra)), "nomess.json")
            expect(False, "docs_root / lessons_dir 落在对外文档里应是配置错误: %r" % extra)
        except ValueError:
            pass


def t_old_site_fallback(tmp):
    """合起来审查 3b:老配置(没写 public_docs)+ 根上 mkdocs.yml(源目录缺省 docs):网站页新增不报 DOC4 红、整理不可写;nomess 类型位置上的页照常管。"""
    import doctypes
    import dream
    import nm_config
    import snapshot
    root = mkrepo(tmp, "dtsite", {}, [("mkdocs.yml", "site_name: x\n"), ("docs/systems/core.md", "# core\n")])
    base = commit(root)
    put(root, "docs/guide.md", "# 网站页\n")
    commit(root)
    p, f = doc4(root, base)
    expect(not f, "网站源目录里的页不该报 DOC4: %r" % [(i["file"], i["level"]) for i in f])
    with snapshot.open_snapshot(root, "tree", "HEAD") as snap:
        site = doctypes.site_dir(snap)
        exp = nm_config.expanded(nm_config.load_snapshot(snap))
    expect(site == "docs", "应认出 mkdocs 的源目录 docs: %r" % site)
    expect(not dream.writable("docs/guide.md", exp, site), "网站页整理不可写")
    expect(dream.writable("docs/systems/core.md", exp, site), "类型位置上的页照常可写")


def t_bad_config(tmp):
    bad = [[{"name": "a", "dir": "docs/a/b", "what": "w"}],      # 不是一层
           [{"name": "a", "dir": "docs/systems", "what": "w"}],  # 和内置重叠
           [{"name": "a", "dir": "docs/lessons", "what": "w"}],
           [{"name": "a", "dir": "src/a", "what": "w"}],
           [{"name": "a", "dir": "docs/a"}],                     # what 必填
           [{"name": "a", "dir": "docs/a", "what": "w"}, {"name": "b", "dir": "docs/a", "what": "w"}]]
    for n, dt in enumerate(bad):
        root = mkrepo(tmp, "dtbad%d" % n, {"doc_types": dt})
        p = nm(root, "check")
        expect(p.returncode == 2 and "Traceback" not in p.stderr, "doc_types 写错应退出 2: %r" % dt)
    root = mkrepo(tmp, "dtdream", {"dream": {"max_items": 0}})
    expect(nm(root, "check").returncode == 2, "dream.max_items 非正整数应退出 2")
    root = mkrepo(tmp, "dtdream2", {"dream": {"auto": False, "max_items": 5}})
    expect(nm(root, "check").returncode == 0, "合法的 dream 配置应通过")


def t_index_deterministic(tmp):
    files = [("docs/overview.md", INDEX_OVERVIEW),
             ("docs/systems/core.md", "# core\n这是什么：核心模块。更多说明。\n"),
             ("docs/plans/new.md", "状态: 提案\n\n# 新方案\n新方案的第一句。第二句。\n"),
             ("docs/plans/archive/2026-01-01-old.md", "状态: 已被取代\n被取代: ../new.md\n\n# 旧方案\n旧的。\n"),
             ("docs/lessons/core.md", "# 教训\n\n## a\n概述: x\n内容: y\n\n## b\n概述: x\n内容: y\n"),
             ("docs/lessons/README.md", "# 教训\n<!-- GEN:l BEGIN -->\n<!-- GEN:l END -->\n"),
             ("docs/stray/z.md", "# 散放\n散放的一页。\n")]
    root = mkrepo(tmp, "dt3", GEN, files)
    nm(root, "docgen")
    a = read(root, "docs/overview.md")
    for want in ("[core](systems/core.md) — 核心模块。", "状态:提案", "→ 被 ../new.md 取代", "[教训索引](lessons/README.md) — 2 条", "未归类", "[散放](stray/z.md) — 散放的一页。"):
        expect(want in a, "目录段缺 %r: %s" % (want, a))
    expect("[新方案](plans/new.md)" in a and "lessons/core.md" not in a, "方案列出、教训只给索引链接")
    nm(root, "docgen")
    expect(read(root, "docs/overview.md") == a and nm(root, "docgen", "--check").returncode == 0, "两次生成应逐字节相同")
    # 归档方案多了超过预算:收成 N 份 + 最新 5 份
    for i in range(40):
        put(root, "docs/plans/archive/2026-02-%02d-p%d.md" % (i % 28 + 1, i), "状态: 已采纳\n\n# 方案 %d\n%s。\n" % (i, "很长的一句话" * 8))
    nm(root, "docgen")
    b = read(root, "docs/overview.md")
    expect("归档方案 41 份;最新 5 份" in b and b.count("](plans/archive/") == 5, "超预算应收成 N 份 + 最新 5 份: %s" % b)
    nm(root, "docgen")
    expect(read(root, "docs/overview.md") == b, "收起后两次生成也应逐字节相同")


def t_type_index_fold(tmp):
    """目录收完归档仍超 -> 有多页的类型收成一行并新建类型索引页;页数少 -> 不建。"""
    plan = lambda i: ("docs/plans/p%02d.md" % i, "状态: 提案\n\n# 方案 %d\n%s。\n" % (i, "很长的一句话" * 8))
    root = mkrepo(tmp, "dt_fold", GEN, [("docs/overview.md", INDEX_OVERVIEW), ("docs/systems/core.md", "# core\n核心。\n")] + [plan(i) for i in range(60)])
    nm(root, "docgen")
    ov, idx = read(root, "docs/overview.md"), "docs/plans/README.md"
    expect("- 方案 — 60 份,见 [plans/README.md](plans/README.md)" in ov and "](plans/p00.md)" not in ov, "目录应把方案收成一行: %s" % ov[:400])
    expect("[core](systems/core.md)" in ov, "只有一页的类型照旧直接链")
    expect(os.path.isfile(os.path.join(root, idx)) and "<!-- GEN:type-index BEGIN -->" in read(root, idx) and "](p00.md)" in read(root, idx), "应新建带 type-index 段的 plans/README.md")
    expect(nm(root, "docgen", "--check").returncode == 0, "生成后再查不应过时")
    small = mkrepo(tmp, "dt_small", GEN, [("docs/overview.md", INDEX_OVERVIEW), plan(0), plan(1)])
    nm(small, "docgen")
    expect(not os.path.exists(os.path.join(small, idx)), "页数少不该建类型索引页")


def t_type_index_handwritten(tmp):
    """项目原有的手写 plans/README.md(无 type-index 标记):溢出时 plans 不收成一行、手写内容不被改。"""
    plan = lambda i: ("docs/plans/p%02d.md" % i, "状态: 提案\n\n# 方案 %d\n%s。\n" % (i, "很长的一句话" * 8))
    hand = "# 方案说明\n手写的,别动。\n"
    root = mkrepo(tmp, "dt_hand", GEN, [("docs/overview.md", INDEX_OVERVIEW), ("docs/plans/README.md", hand)] + [plan(i) for i in range(60)])
    nm(root, "docgen")
    ov = read(root, "docs/overview.md")
    expect("见 [plans/README.md]" not in ov and "](plans/p00.md)" in ov, "无标记的 README 不该收类型")
    expect(read(root, "docs/plans/README.md") == hand, "手写 README 内容不该被改")


def t_orphans(tmp):
    root = mkrepo(tmp, "dt4", {}, [("docs/overview.md", "# 总览\n[a](systems/a.md)\n"), ("docs/systems/a.md", "# a\n[b](b.md)\n"),
                                  ("docs/systems/b.md", "# b\n"), ("docs/systems/c.md", "# c\n"), ("docs/systems/d.md", "# d\n"),
                                  ("docs/plans/archive/x.md", "# x\n"), ("docs/system-map/index.md", "# map\n")])
    p = nm(root, "check", "--all", "--json")
    f = [i for i in json.loads(p.stdout) if i["rule"] == "DOC5"]
    expect(len(f) == 1 and f[0]["level"] in YELLOW and "2" in f[0]["msg"] and "systems/c.md" in f[0]["msg"] and "archive" not in f[0]["msg"]
           and "init --auto" in f[0]["msg"], "孤儿页应合成一条黄(2 个,不含归档和系统图,没目录段带提示): %r" % f)
    put(root, "docs/overview.md", INDEX_OVERVIEW.replace("systems/core.md", "systems/a.md"))
    cfg = json.loads(read(root, "nomess.json"))
    cfg.update(GEN)
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    nm(root, "docgen")
    expect(not [i for i in json.loads(nm(root, "check", "--all", "--json").stdout) if i["rule"] == "DOC5"], "目录段生成后不该再有孤儿页")


def t_review_must(tmp):
    lesson = "# 教训\n\n## 外部的坑\n概述: s\n状态: 未核实\n来源: 外部 https://x\n内容: y\n"
    root = mkrepo(tmp, "dt5", {}, [("docs/lessons/core.md", lesson), ("docs/systems/a.md", "# a\n")])
    base = commit(root)
    put(root, "docs/lessons/core.md", lesson.replace("来源: 外部 https://x\n", ""))
    cfg = json.loads(read(root, "nomess.json"))
    cfg["doc_types"] = [{"name": "api", "dir": "docs/api", "what": "接口"}]
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    commit(root)
    out = nm(root, "review-input", base).stdout
    expect("[must-review]" in out and "L6" in out and "外部的坑" in out and "新增 doc_types 条目" in out, "必审项应含 L6 和新增 doc_types: %s" % out[:600])
    # 状态改成已核实也算
    put(root, "docs/lessons/core.md", lesson)
    base2 = commit(root)  # 回到带来源、未核实的状态作新基准
    put(root, "docs/lessons/core.md", lesson.replace("未核实", "已核实"))
    commit(root)
    out = nm(root, "review-input", base2).stdout
    expect("L6" in out and "已核实" in out, "外部条目改成已核实应进必审: %s" % out[:400])


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
