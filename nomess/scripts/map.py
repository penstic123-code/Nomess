"""系统图:生成 <docs_root>/system-map/ 下的首页和分页,全部生成、不手改。
  index.md  分页链接 / 重叠热点清单(末行"屎山存量 N")/ 每个子系统一行 / 子系统依赖图(Mermaid)
  files.md  文件清单(git ls-files + 头注释第一句)      deps.md  仓库内文件依赖(六种语言,内置)
  <表名>.md 每个 nomess.json "map" 抽取表一页:标题 + 列名 + 文件 glob + 正则(每个捕获组一列,每处匹配一行)+ 会漏什么;
            可带 hotspot {by: 列名, max: 数, label: 说明}:按这一列分组,不同文件数超过 max 算热点(需 file_col)。
size 为 small 时只出首页(不带分页链接)。files.md、deps.md 超 map.page_tokens(缺省 8000)时收法:files.md 每个目录一行(文件数),
deps.md 只列跨子系统的边。抽取表也可作 docgen 生成器:{"file": "...", "map": "<抽取表名>"}。
子系统划分见 nomess.json 的 "systems"(名字 → 路径 glob 列表);没填就按源文件所在的顶层目录划;一个文件匹配两个子系统 -> 配置错误。
首页有 token 预算(map.index_tokens,缺省 1500),超了按固定顺序裁:先子系统图只留参与跨子系统依赖的节点,再热点清单只留最重的 10 条。
抽取表的逐文件命中经 cache.facts 缓存(kind map.table,version 带表配置的哈希)。
"""
import hashlib
import json
import os
import posixpath
import re

import cache
import deps
import docgen
import messages
import nm_config
import outwrite
import pathglob
import snapshot
from messages import alts, t
from nm_config import est_tokens

M = {
    "MP_OVERLAP": ("systems: %s matches both %s and %s; a file belongs to one subsystem only",
                   "systems:%s 同时匹配 %s 和 %s;一个文件只能属于一个子系统"),
    "MP_HOT_LINE": ("- %s: `%s` (%d files: %s; table %s)", "- %s:`%s`(%d 个文件:%s;表 %s)"),
    "MP_HOT_DEPS": ("- depended on by too many: `%s` (%d files depend on it)", "- 被依赖过多:`%s`(%d 个文件依赖它)"),
    "MP_REST": ("- %d more not listed", "- 其余 %d 条从略"),
    "MP_DEBT": ("- frozen findings (existing mess): %d (see %s)", "- 屎山存量 %d 条(已冻结的检查发现,见 %s)"),
    "MP_FILES_DIRS": ("**Files** (%d, over the page budget: one line per directory)", "**文件清单**(%d 个,超过分页预算:每个目录一行)"),
    "MP_FILES_DIRS_COLS": ("| Directory | Files |", "| 目录 | 文件数 |"),
    "MP_DEPS_CROSS": ("**File dependencies** (%d, over the page budget: only the %d crossing subsystems)",
                      "**文件依赖**(%d 条,超过分页预算:只列跨子系统的 %d 条)"),
}
messages.add(M)

RESERVED = ("index", "files", "deps")


def out_dir(cfg):
    """系统图目录:<docs_root>/system-map(生成物跟项目文档在一个根下)。"""
    return nm_config.docs_root(cfg) + "/system-map"

INDEX_TOKENS = 1500    # 首页预算缺省值
HOT_KEEP = 10          # 超预算时热点清单留这么多条


def files_of(snap, pattern):
    """git 管着的文件里匹配 pattern 的(相对路径);glob 语义同规则文件(pathglob),map 抽取表和 check 规则共用。"""
    match = pathglob.matcher([pattern])
    return [n for n in deps.all_files(snap) if match(n)]


def tables_of(cfg):
    """nomess.json 的 map 段里的抽取表(index_tokens、page_tokens 是预算,不是表)。"""
    return {k: v for k, v in cfg.get("map", {}).items() if isinstance(v, dict)}


def systems_of(cfg, names):
    """子系统表 名字 → glob 列表:nomess.json 的 systems;没填就按 names 里源文件(deps.sources)的顶层目录划(隐藏目录除外,只有文档的目录不算),derived 为真。"""
    if cfg.get("systems"):
        return cfg["systems"], False
    tops = sorted({n.split("/")[0] for n in deps.sources(names) if "/" in n and not n.startswith(".")})
    return {t: [t + "/**"] for t in tops}, True


def owners_of(systems, names):
    """{文件: 子系统名}(不属于任何子系统的不列);glob 语义同规则文件。一个文件匹配两个子系统 -> ValueError(配置错误,报出文件)。
    子系统归属的唯一入口:系统图和 arch 都用它。"""
    # 按 glob 的首段分桶:首段是字面量的只试首段相同的文件,其余每个文件都试;免得 文件数 × glob 数 全量匹配
    order = {name: i for i, name in enumerate(systems)}
    by_top, anywhere = {}, []
    for name, globs in systems.items():
        for g in globs:
            top = pathglob.literal_top(g)
            (anywhere if top is None else by_top.setdefault(top, [])).append((name, pathglob.compile(g)))
    out = {}
    for f in names:
        hit = sorted({name for name, rx in by_top.get(f.split("/")[0], []) + anywhere if rx.match(f)}, key=order.get)
        if len(hit) > 1:
            raise ValueError(t("MP_OVERLAP", f, hit[0], hit[1]))
        if hit:
            out[f] = hit[0]
    return out


def _spec(cfg, name):
    spec = tables_of(cfg).get(name)
    if spec is None:
        raise KeyError(t("MAP_NO_TABLE", name, ", ".join(tables_of(cfg))))
    hs = spec.get("hotspot")
    if hs and (hs.get("by") not in spec["columns"] or not spec.get("file_col") or not hs.get("max") or not hs.get("label")):
        raise ValueError(t("MAP_HOTSPOT", name))
    return spec


def rows_of(snap, cfg, name):
    """(表定义, [[各捕获组的值(去首尾空白,没匹配到的组为空)..., 文件]])。逐文件命中经缓存,键带表配置的哈希。"""
    spec = _spec(cfg, name)
    rx = re.compile(spec["regex"], re.M)
    if rx.groups != len(spec["columns"]):
        raise ValueError(t("MAP_GROUPS", name, rx.groups, len(spec["columns"])))
    version = name + "@" + hashlib.sha1(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    hits = lambda text: [[(g or "").strip() for g in m.groups()] for m in rx.finditer(text)]  # noqa: E731
    rows = []
    for rel in files_of(snap, spec["glob"]):
        rows += [r + [rel] for r in cache.facts(snap, rel, "map.table", version, hits)]
    return spec, rows


def _cell(s):
    return s.replace("|", "\\|")


def generate(snap, cfg, name):
    spec, rows = rows_of(snap, cfg, name)
    with_file = spec.get("file_col", False)
    head = list(spec["columns"]) + ([t("MAP_FILE_COL")] if with_file else [])
    body = sorted([_cell(c) for c in (r if with_file else r[:-1])] for r in rows)
    out = [t("MAP_ROWS", spec["title"], len(body)), "",
           "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in body]
    if spec.get("misses"):
        out += ["", t("MAP_MISSES") + spec["misses"]]
    return "\n".join(out)


def _files_page(snap, files, budget):
    out = [t("MAP_FILES", len(files)), "", t("MAP_FILES_COLS"), "|---|---|"]
    out += ["| %s | %s |" % (_cell(f), _cell(deps.header(snap, f) or "—")) for f in files]
    text = "\n".join(out)
    if est_tokens(text) <= budget:
        return text
    dirs = {}
    for f in files:
        d = posixpath.dirname(f) or "."
        dirs[d] = dirs.get(d, 0) + 1
    out = [t("MP_FILES_DIRS", len(files)), "", t("MP_FILES_DIRS_COLS"), "|---|---|"]
    return "\n".join(out + ["| %s | %d |" % (_cell(d), n) for d, n in sorted(dirs.items())])


def _deps_page(es, owner, budget):
    out = [t("MAP_DEPS", len(es)), "", t("MAP_DEPS_COLS"), "|---|---|"]
    rows = ["| %s | %s |" % (_cell(a), _cell(b)) for a, b in sorted(es)]
    text = "\n".join(out + rows)
    if est_tokens(text) <= budget:
        return text
    cross = sorted((a, b) for a, b in es if owner.get(a) and owner.get(b) and owner[a] != owner[b])
    out = [t("MP_DEPS_CROSS", len(es), len(cross)), "", t("MAP_DEPS_COLS"), "|---|---|"]
    return "\n".join(out + ["| %s | %s |" % (_cell(a), _cell(b)) for a, b in cross])


def _hotspots(snap, cfg, es, linked):
    """[(涉及文件数, 一行文字)],按登记顺序;linked 为假(没有分页)时不带分页链接。"""
    out = []
    for name, spec in tables_of(cfg).items():
        hs = spec.get("hotspot")
        if not hs:
            continue
        _, rows = rows_of(snap, cfg, name)
        col = spec["columns"].index(hs["by"])
        groups = {}
        for r in rows:
            groups.setdefault(r[col], set()).add(r[-1])
        for val, fs in sorted(groups.items()):
            if len(fs) > hs["max"]:
                args = (hs["label"], val, len(fs), ", ".join(sorted(fs)), spec["title"])
                out.append((len(fs), t("MAP_HOT_LINE", *args, name) if linked else t("MP_HOT_LINE", *args)))
    fan_in = {}
    for _, dst in es:
        fan_in[dst] = fan_in.get(dst, 0) + 1
    limit = nm_config.expanded(cfg)["smells"]["fan_in"]
    out += [(n, t("MAP_HOT_DEPS" if linked else "MP_HOT_DEPS", f, n)) for f, n in sorted(fan_in.items()) if n > limit]
    return out


def _system_line(snap, cfg, name, derived):
    page = snap.text("%s/systems/%s.md" % (nm_config.docs_root(cfg), name))
    if page is None:
        return "- **%s**" % name if derived else t("MAP_SYS_NOPAGE", name, nm_config.docs_root(cfg), name)
    m = re.search(r"^(?:%s)[:：]\s*(.+)$" % "|".join(alts("system_head", "what")), page, re.M)
    return t("MAP_SYS_LINE", name, m.group(1).strip() if m else t("MAP_SYS_NOWHAT"), name)


def _mermaid(systems, owner, es, only_linked):
    """子系统依赖图,只画跨子系统的边;only_linked 为真时再去掉没有任何边的节点。"""
    agg = sorted((a, b) for a, b in {(owner.get(x), owner.get(y)) for x, y in es} if a and b and a != b)
    names = [n for n in systems if not only_linked or any(n in e for e in agg)]
    ids = {n: "S%d" % i for i, n in enumerate(names)}
    out = ["```mermaid", "flowchart LR"]
    out += ['  %s["%s"]' % (ids[n], n.replace('"', "'")) for n in names]
    out += ["  %s --> %s" % (ids[a], ids[b]) for a, b in agg]
    out.append("```")
    return "\n".join(out)


def check_table_names(tables):
    """表名要当文件名用:单个安全片段,不含路径分隔符和 Windows 非法字符,不叫 . / .. / 设备名,不与内置分页或彼此重名(不分大小写)。
    在写任何页之前校验。"""
    seen = set(RESERVED)
    for n in tables:
        if not n or re.search(r'[\\/:*?"<>|\x00-\x1f]', n) or n != n.strip(" .") or re.fullmatch(r"(?i)con|prn|aux|nul|com\d|lpt\d", n):
            raise ValueError(t("MAP_NAME_BAD", n))
        if n.lower() in seen:
            raise ValueError(t("MAP_NAME_DUP", n, ", ".join(RESERVED)))
        seen.add(n.lower())


def pages(snap, cfg):
    """{相对仓库根的路径: 内容};size 为 small 时只有首页。"""
    tables = tables_of(cfg)
    check_table_names(tables)
    exp = nm_config.expanded(cfg)
    names = deps.all_files(snap)
    files = deps.sources(names)
    es = deps.edges(snap, files)
    systems, derived = systems_of(cfg, names)
    owner = owners_of(systems, names)
    linked = exp["size"] != "small"
    od = out_dir(cfg)
    out = {}
    if linked:
        budget = exp["map"]["page_tokens"]
        out = {od + "/files.md": _files_page(snap, files, budget), od + "/deps.md": _deps_page(es, owner, budget)}
        for name in tables:
            out["%s/%s.md" % (od, name)] = generate(snap, cfg, name)
    out[od + "/index.md"] = _index(snap, cfg, tables if linked else {}, es, systems, derived, owner, linked)
    return out


def _debt(snap, cfg):
    """首页热点清单末行:已提交基线的条目数(check.load_baseline;check 在顶层 import 了本模块,这里按需导入)。"""
    import check
    n = sum(len(v) for v in check.load_baseline(snap, cfg).values())
    return t("MP_DEBT", n, nm_config.expanded(cfg)["check"]["baseline"])


def _index(snap, cfg, tables, es, systems, derived, owner, linked):
    hot = _hotspots(snap, cfg, es, linked)
    budget = cfg.get("map", {}).get("index_tokens", INDEX_TOKENS)
    debt = _debt(snap, cfg)

    def build(only_linked, hot_lines):
        idx = [t("MAP_IDX_TITLE"), ""]
        if linked:
            idx += [t("MAP_IDX_PAGES"), t("MAP_IDX_FILES"), t("MAP_IDX_DEPS")]
            idx += ["- [%s](%s.md)" % (spec["title"], n) for n, spec in tables.items()]
            idx.append("")
        idx += [t("MAP_IDX_HOT")] + (hot_lines or [t("MAP_IDX_NONE")]) + [debt]
        if systems:
            idx += ["", t("MAP_IDX_SYS")] + [_system_line(snap, cfg, n, derived) for n in systems]
            idx += ["", t("MAP_IDX_SYSDEPS"), _mermaid(systems, owner, es, only_linked)]
        return "\n".join(idx)

    full = [line for _, line in hot]
    heavy = [line for _, line in sorted(hot, key=lambda h: (-h[0], h[1]))]
    rest = t("MAP_IDX_REST" if linked else "MP_REST", len(heavy) - HOT_KEEP)
    cut = heavy[:HOT_KEEP] + ([rest] if len(heavy) > HOT_KEEP else [])
    text = ""
    for only_linked, lines in ((False, full), (True, full), (True, cut)):  # 固定裁法:先收子系统图,再裁热点
        text = build(only_linked, lines)
        if est_tokens(text) <= budget:
            break
    return text


def plan(snap, cfg):
    """{路径: 新内容 bytes | None(删多余的旧页)}:生成结果和快照比(docgen.same,不计换行差别),只含要改的。
    不写盘(落盘走 outwrite.apply)。"""
    new = {k: (v.rstrip("\n") + "\n") for k, v in pages(snap, cfg).items()}
    out = {}
    for rel, text in sorted(new.items()):
        old = snap.text(rel)
        if old is None or not docgen.same(old, text):
            out[rel] = text.encode("utf-8")
    out.update(dict.fromkeys(p for p in snap.ls(out_dir(cfg), ".md") if p not in new))
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess map", description="generate the <docs_root>/system-map/ index and pages")
    ap.add_argument("--check", action="store_true", help="compare only, do not write; exit 1 if any page is stale")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    base = os.path.dirname(config)
    with snapshot.open_snapshot(base, "worktree") as snap:
        cfg = nm_config.load(config)
        changed = plan(snap, cfg)
    if not a.check:
        outwrite.apply(base, changed)
        outwrite.prune_empty(base, out_dir(cfg))
    for rel in changed:
        print("%s %s" % (t("STALE") if a.check else t("WRITTEN"), rel))
    return 1 if a.check and changed else 0
