"""子系统之间的约束(设计稿 ⑥ 第 2 小节):系统图已经抽出来的关系(依赖图、抽取表)× nomess.json 的 arch 登记 -> 集合运算。
  A1 子系统成环(内置依赖图;只由 Python import 边成的环红,含别的语言边的黄)  A2 下层依赖上层(arch.layers,第 0 层最上)
  A3 声明独立的子系统互相依赖(arch.independent)  A4 点名禁止的依赖(arch.forbid: {from, to, why})
  arch.relations 两种 kind,规则号就是条目的 id:single_writer(table 的每个值只许一个子系统写,写了 owner 就必须是它;
  原 A5)、needs(from 里的每个值 to 里也要有,same_system 时还得同一子系统)。
  REL_EMPTY 红色关系引用的表一行都没抽到(表上 may_be_empty: true 的除外);UNOWNED 不属于任何子系统、因而不参与约束的文件条数(黄)。
归属按 map.owners_of(唯一入口,一个文件匹配两个子系统 -> 配置错误);不属于任何子系统的文件不参与约束。
登记写错(子系统名不存在、表名列名不存在、同一列两条 single_writer、形状不对)抛 ValueError(退出 2)。
跨子系统的环只报 A1:落在环上的 A2 / A3 边带 under=("A1", 环),A1 会挡提交时不再逐边报。
另有 docgen 内置生成器 owners:从 single_writer 生成归属图的主人表。"""
import deps
import map as nm_map
import messages
import nm_config
from messages import t
from nm_config import F

M = {
    "AR_A1_WHAT": ("subsystems must not form a dependency cycle", "子系统之间不许成环"),
    "AR_A1_WHY": ("a cycle means no subsystem can change or be tested alone", "成环就没有哪个子系统能单独改、单独测"),
    "AR_A2_WHAT": ("a lower layer must not depend on a higher one (arch.layers)", "下层不许依赖上层(arch.layers)"),
    "AR_A2_WHY": ("upward dependencies make the layering meaningless", "往上依赖,分层就形同虚设"),
    "AR_A3_WHAT": ("subsystems declared independent must not depend on each other (arch.independent)",
                   "声明独立的子系统不许互相依赖(arch.independent)"),
    "AR_A3_WHY": ("they are meant to change and ship separately", "它们本该各改各的"),
    "AR_A4_WHAT": ("dependencies named in arch.forbid", "arch.forbid 点名禁止的依赖"),
    "AR_A4_WHY": ("the project said so; the reason is in each entry", "项目登记过,理由写在条目里"),
    "AR_REL_EMPTY_WHAT": ("a table used by a red relation extracted no rows", "红色关系引用的表一行都没抽到"),
    "AR_REL_EMPTY_WHY": ("the regex probably stopped matching, so the relation checks nothing", "正则多半失效了,这条关系等于没查"),
    "AR_UNOWNED_WHAT": ("files outside every subsystem", "不属于任何子系统的文件"),
    "AR_UNOWNED_WHY": ("constraints between subsystems do not see them", "子系统间的约束看不到它们"),
    "AR_A1": ("subsystem cycle %s (%s)", "子系统成环 %s(%s)"),
    "AR_A1_APPROX": ("; includes non-Python edges, which are regex approximations", ";含非 Python 的边,是正则近似的"),
    "AR_A2": ("%s (layer %d) depends on %s (layer %d, above it): %s", "%s(第 %d 层)依赖了上层的 %s(第 %d 层):%s"),
    "AR_A3": ("%s and %s are declared independent: %s", "%s 和 %s 声明了互相独立:%s"),
    "AR_A4": ("%s must not depend on %s (%s): %s", "%s 不许依赖 %s(%s):%s"),
    "AR_SW_OWNER": ("%s: %s = %s is written in %s; its owner is %s", "%s:%s = %s 在 %s 里写,主人是 %s"),
    "AR_SW_MANY": ("%s: %s = %s is written by several subsystems: %s", "%s:%s = %s 有多个子系统写:%s"),
    "AR_NEEDS": ("%s: %s = %s has no match in %s", "%s:%s = %s 在 %s 里没有"),
    "AR_NEEDS_SAME": ("%s: %s = %s has no match in %s within subsystem %s", "%s:%s = %s 在 %s 里没有同属 %s 的"),
    "AR_REL_EMPTY": ("relation %s: table %s extracted no rows (regex broken? write may_be_empty: true on the table if zero rows is legal)",
                     "关系 %s:表 %s 一行都没抽到(正则失效了?合法为零行就在表上写 may_be_empty: true)"),
    "AR_UNOWNED": ("%d files are in no subsystem and take part in no constraint (e.g. %s)",
                   "%d 个文件不属于任何子系统,不参与约束(例如 %s)"),
    "AR_BAD": ("nomess.json arch.%s is invalid: %s", "nomess.json 的 arch.%s 写法不对:%s"),
    "AR_NO_SYS": ("nomess.json arch.%s: %s is not a subsystem (have: %s)", "nomess.json 的 arch.%s:%s 不是子系统(有: %s)"),
    "AR_NO_COL": ("nomess.json arch.relations %s: %s is not table.column of a map table (tables: %s)",
                  "nomess.json 的 arch.relations %s:%s 不是 map 抽取表的 表.列(有表: %s)"),
    "AR_DUP_WRITER": ("nomess.json arch.relations: %s has two single_writer entries (%s, %s)",
                      "nomess.json 的 arch.relations:%s 登记了两条 single_writer(%s、%s)"),
    "AR_OWNERS_COLS": ("| Data (table.column) | Owner | Rule | What |", "| 数据(表.列) | 主人 | 规则 | 说明 |"),
    "AR_OWNERS_ANY": ("any one subsystem", "任一个子系统(只许一个)"),
    "AR_OWNERS_NONE": ("(no single_writer relations in nomess.json)", "(nomess.json 里没有 single_writer 关系)"),
}
messages.add(M)

RULES = [
    {"id": "A1", "level": "red", "what": "AR_A1_WHAT", "why": "AR_A1_WHY"},
    {"id": "A2", "level": "red", "what": "AR_A2_WHAT", "why": "AR_A2_WHY", "select": "edge",
     "needs": lambda c: bool(c["arch"]["layers"])},
    {"id": "A3", "level": "red", "what": "AR_A3_WHAT", "why": "AR_A3_WHY", "select": "edge",
     "needs": lambda c: bool(c["arch"]["independent"])},
    {"id": "A4", "level": "red", "what": "AR_A4_WHAT", "why": "AR_A4_WHY", "select": "edge",
     "needs": lambda c: bool(c["arch"]["forbid"])},
    {"id": "REL_EMPTY", "level": "red", "what": "AR_REL_EMPTY_WHAT", "why": "AR_REL_EMPTY_WHY", "freeze": False,
     "needs": lambda c: bool(c["arch"]["relations"])},
    {"id": "UNOWNED", "level": "yellow", "what": "AR_UNOWNED_WHAT", "why": "AR_UNOWNED_WHY", "freeze": False,
     "needs": lambda c: registered(c["arch"])},
]
RELATIONS = True  # arch.relations 的号由本模块产出
REL_BASE = ("id", "level", "what", "why", "kind")
REL_KEYS = {"single_writer": REL_BASE + ("table", "owner"), "needs": REL_BASE + ("from", "to", "same_system")}


def registered(arch):
    return any(arch[k] for k in ("layers", "independent", "forbid", "relations"))


# ---------------------------------------------------------------- 登记校验(arch 段内部)

def _str(v):
    return isinstance(v, str) and v.strip() != ""


def _col(ref, rid, tables):
    """'表.列' -> (表名, 列序号);表名不能含点。不存在 -> ValueError。"""
    table, _, col = ref.partition(".") if isinstance(ref, str) else ("", "", "")
    spec = tables.get(table)
    if spec is None or col not in spec["columns"]:
        raise ValueError(t("AR_NO_COL", rid, ref, ", ".join(tables)))
    return table, spec["columns"].index(col)


def validate(arch, systems, tables):
    """arch 段(展开后)对照子系统名和抽取表;不对就 ValueError。"""
    def known(where, name):
        if name not in systems:
            raise ValueError(t("AR_NO_SYS", where, name, ", ".join(sorted(systems))))

    seen = set()
    for i, layer in enumerate(arch["layers"]):
        if not isinstance(layer, list) or not layer or not all(_str(x) for x in layer):
            raise ValueError(t("AR_BAD", "layers[%d]" % i, layer))
        for x in layer:
            known("layers", x)
            if x in seen:
                raise ValueError(t("AR_BAD", "layers", x))
            seen.add(x)
    if not all(_str(x) for x in arch["independent"]) or len(set(arch["independent"])) != len(arch["independent"]):
        raise ValueError(t("AR_BAD", "independent", arch["independent"]))
    for x in arch["independent"]:
        known("independent", x)
    for i, fb in enumerate(arch["forbid"]):
        if not isinstance(fb, dict) or set(fb) != {"from", "to", "why"} or not all(_str(fb[k]) for k in fb):
            raise ValueError(t("AR_BAD", "forbid[%d]" % i, fb))
        known("forbid", fb["from"])
        known("forbid", fb["to"])
    writers = {}
    for i, r in enumerate(arch["relations"]):
        ok = isinstance(r, dict) and r.get("kind") in REL_KEYS and set(r) <= set(REL_KEYS[r["kind"]]) \
            and all(_str(r.get(k)) for k in ("id", "what", "why")) and r.get("level") in ("red", "yellow")
        if ok and r["kind"] == "single_writer":
            ok = _str(r.get("table")) and ("owner" not in r or _str(r["owner"]))
        elif ok:
            ok = _str(r.get("from")) and _str(r.get("to")) and isinstance(r.get("same_system", False), bool)
        if not ok:
            raise ValueError(t("AR_BAD", "relations[%d]" % i, r))
        if r["kind"] == "single_writer":
            _col(r["table"], r["id"], tables)
            if "owner" in r:
                known("relations " + r["id"], r["owner"])
            if r["table"] in writers:
                raise ValueError(t("AR_DUP_WRITER", r["table"], writers[r["table"]], r["id"]))
            writers[r["table"]] = r["id"]
        else:
            _col(r["from"], r["id"], tables)
            _col(r["to"], r["id"], tables)


# ---------------------------------------------------------------- 图

def _sccs(nodes, adj):
    """强连通分量(Tarjan),只留两个以上成员的;成员排好序,分量按成员排序。"""
    index, low, stack, on, out, n = {}, {}, [], set(), [], [0]

    def visit(v):
        index[v] = low[v] = n[0]
        n[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(adj.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))
    for v in sorted(nodes):
        if v not in index:
            visit(v)
    return sorted(out)


def _cycle(comp, adj):
    """分量里从第一个成员出发回到它的一条最短环(广度优先)-> [a, b, ..., a]。"""
    start, members = comp[0], set(comp)
    prev, queue = {start: None}, [start]
    for v in queue:
        for w in sorted(adj.get(v, ())):
            if w == start:
                path = [v]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return path[::-1] + [start]
            if w in members and w not in prev:
                prev[w] = v
                queue.append(w)
    raise AssertionError("component without a cycle")


def _cycles(sys_edges):
    """-> [(颜色, 成员, 环路径)]:只由 Python import 边(源文件 .py,ast 取的)成的环红;所有边上的环里没有同成员红环的黄。"""
    adj_all, adj_py = {}, {}
    for (a, b), fe in sys_edges.items():
        adj_all.setdefault(a, set()).add(b)
        if any(src.endswith(".py") for src, _, _ in fe):
            adj_py.setdefault(a, set()).add(b)
    nodes = {x for e in sys_edges for x in e}
    red = _sccs(nodes, adj_py)
    out = [("red", c, _cycle(c, adj_py)) for c in red]
    out += [("yellow", c, _cycle(c, adj_all)) for c in _sccs(nodes, adj_all) if c not in red]
    return out


def model(snap, cfg):
    """(owner {文件: 子系统}, 文件依赖边 {(源, 被依赖): 行}, 子系统间的边 {(a, b): [(源文件, 被依赖文件, 行)]}, 抽取表)。
    登记不对抛 ValueError。"""
    names = deps.all_files(snap)
    systems, _ = nm_map.systems_of(cfg, names)
    tables = nm_map.tables_of(cfg)
    validate(cfg["arch"], systems, tables)
    owner = nm_map.owners_of(systems, names)
    es = deps.edges(snap, deps.sources(names))
    sys_edges = {}
    for (src, dst), line in sorted(es.items()):
        a, b = owner.get(src), owner.get(dst)
        if a and b and a != b:
            sys_edges.setdefault((a, b), []).append((src, dst, line))
    return owner, es, sys_edges, tables


# ---------------------------------------------------------------- 检测

def _edge_findings(arch, sys_edges, cycles):
    rank = {x: i for i, layer in enumerate(arch["layers"]) for x in layer}
    indep = set(arch["independent"])
    forbid = {}
    for fb in arch["forbid"]:
        forbid.setdefault((fb["from"], fb["to"]), fb["why"])
    on_cycle = {}  # (a, b) -> 所在环的成员;红环优先(只有会挡提交的 A1 才让 A2 / A3 让路)
    for color, comp, _ in sorted(cycles, key=lambda c: c[0] != "red"):
        for a in comp:
            for b in comp:
                on_cycle.setdefault((a, b), comp)
    out = []
    for (a, b), fe in sorted(sys_edges.items()):
        under = ("A1", on_cycle[(a, b)]) if (a, b) in on_cycle else None
        hits = []
        if a in rank and b in rank and rank[b] < rank[a]:
            hits.append(("A2", lambda ex: t("AR_A2", a, rank[a], b, rank[b], ex), under))
        if a in indep and b in indep:
            hits.append(("A3", lambda ex: t("AR_A3", a, b, ex), under))
        if (a, b) in forbid:
            hits.append(("A4", lambda ex: t("AR_A4", a, b, forbid[(a, b)], ex), None))
        for rule, msg, und in hits:
            for src, dst, line in fe:
                ex = "%s -> %s" % (src, dst)
                out.append(F("red", rule, src, line, ex, msg(ex), k=[a, b], edge=(a, b), under=und))
    return out


def _relation_findings(snap, cfg, arch, owner, tables):
    """-> (发现, 参与了关系、但不属于任何子系统的文件)。"""
    cache_rows, out, loose = {}, [], set()

    def rows(table):
        if table not in cache_rows:
            cache_rows[table] = nm_map.rows_of(snap, cfg, table)[1]
        return cache_rows[table]

    def col(ref, rid):
        table, i = _col(ref, rid, tables)
        got = []
        for r in rows(table):
            if r[i]:
                if owner.get(r[-1]):
                    got.append((r[i], r[-1], owner[r[-1]]))
                else:
                    loose.add(r[-1])
        return got

    for r in arch["relations"]:
        rid, lv = r["id"], r["level"]
        refs = [r["table"]] if r["kind"] == "single_writer" else [r["from"], r["to"]]
        if lv == "red":
            for table in sorted({x.partition(".")[0] for x in refs}):
                if not rows(table) and not tables[table].get("may_be_empty"):
                    out.append(F("red", "REL_EMPTY", nm_config.CONFIG_NAME, 0, table, t("AR_REL_EMPTY", rid, table), k=[rid, table]))
        if r["kind"] == "single_writer":
            by_val = {}
            for val, f, s in col(r["table"], rid):
                by_val.setdefault(val, []).append((f, s))
            for val, ws in sorted(by_val.items()):
                syss = sorted({s for _, s in ws})
                for f, s in sorted(ws):
                    if "owner" in r and s != r["owner"]:
                        out.append(F(lv, rid, f, 0, val, t("AR_SW_OWNER", r["what"], r["table"], val, s, r["owner"]), k=[r["table"], val]))
                    elif "owner" not in r and len(syss) > 1:
                        out.append(F(lv, rid, f, 0, val, t("AR_SW_MANY", r["what"], r["table"], val, ", ".join(syss)), k=[r["table"], val]))
        else:
            to = col(r["to"], rid)
            have = {(v, s) for v, _, s in to} if r.get("same_system") else {v for v, _, _ in to}
            for val, f, s in sorted(col(r["from"], rid)):
                if r.get("same_system") and (val, s) not in have:
                    out.append(F(lv, rid, f, 0, val, t("AR_NEEDS_SAME", r["what"], r["from"], val, r["to"], s), k=[r["from"], val]))
                elif not r.get("same_system") and val not in have:
                    out.append(F(lv, rid, f, 0, val, t("AR_NEEDS", r["what"], r["from"], val, r["to"]), k=[r["from"], val]))
    return out, loose


def run(snap, changes, eff):
    """按图的检测:整棵树现算(changes 不用)。没开 A1、arch 也没登记任何约束时只查 systems 有没有重叠。"""
    cfg = eff.cfg
    arch = cfg["arch"]
    if "A1" not in cfg["check"]["builtin"] and not registered(arch):
        nm_map.owners_of(cfg["systems"], deps.all_files(snap))  # 归属必须唯一:重叠是配置错误,登没登记约束都查
        return []
    owner, es, sys_edges, tables = model(snap, cfg)
    cycles = _cycles(sys_edges)
    out = []
    for color, comp, path in cycles:
        hops = []
        for a, b in zip(path, path[1:]):
            fe = sys_edges[(a, b)]
            src, dst, line = next((e for e in fe if e[0].endswith(".py")), fe[0]) if color == "red" else fe[0]
            hops.append("%s:%d -> %s" % (src, line, dst))
        msg = t("AR_A1", " -> ".join(path), "; ".join(hops)) + ("" if color == "red" else t("AR_A1_APPROX"))
        out.append(F(color, "A1", "-", 0, " ".join(comp), msg, k=comp))
    if not registered(arch):
        return out
    out += _edge_findings(arch, sys_edges, cycles)
    rel, loose = _relation_findings(snap, cfg, arch, owner, tables)
    out += rel
    loose |= {f for e in es for f in e if f not in owner}
    if loose:
        ex = sorted(loose)
        out.append(F("yellow", "UNOWNED", "-", 0, "unowned", t("AR_UNOWNED", len(ex), ", ".join(ex[:3])), k=[]))
    return out


# ---------------------------------------------------------------- docgen 生成器 owners

def owners(snap, cfg, spec):
    """归属图的主人表(builtin: owners):每条 single_writer 一行,按 表.列 排序;两次生成一字不差。"""
    rels = sorted((r for r in nm_config.expanded(cfg)["arch"]["relations"] if r.get("kind") == "single_writer"),
                  key=lambda r: (r["table"], r["id"]))
    if not rels:
        return t("AR_OWNERS_NONE")
    out = [t("AR_OWNERS_COLS"), "|---|---|---|---|"]
    out += ["| `%s` | %s | %s | %s |" % (r["table"], r.get("owner") or t("AR_OWNERS_ANY"), r["id"], r["what"].replace("|", "\\|"))
            for r in rels]
    return "\n".join(out)
