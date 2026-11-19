"""总排期和方案对账(整棵树的检测,每次读 <docs_root>/schedule.md 和 <docs_root>/plans/*.md):
  C4        并行的包抢同一个文件:两个“在做”重叠红(有依赖也报);“在做”的包依赖未合红;两个“待派”重叠黄。
            红只给确定的重叠:有现存文件同时匹配两边,或两边有字面路径(不带通配符)完全相同;
            只凭 glob 第一个通配符之前的字面前缀推断的重叠(双方都要新建的路径也算)降黄,“在做”也是。
            排期里认不出的行(列数不对、状态值不认识)和不存在的依赖包名各报一条黄(带行号)。
  PL-STALE  没归档的方案(docs/plans/ 下、不在 archive/)里,反引号里的文件路径不存在、方案头 `系统:` 的系统名不在 systems 里,报黄。"""
import posixpath
import re

import deps
import doccheck
import doctypes
import lessons
import map as nm_map
import messages
import nm_config
import pathglob
from messages import code_of, t
from nm_config import F

WILD = re.compile(r"[*?\[]")
M = {
    "PC_C4": ("parallel packages touch the same files", "并行的包抢同一个文件"),
    "PC_C4_WHY": ("two packages that run at once should own disjoint files; list explicit files", "同时在做或待派的包文件要不重叠;并行包尽量列明确文件"),
    "PC_STALE": ("plan mentions a path or system that no longer exists", "方案提到的路径或系统已不存在"),
    "PC_STALE_WHY": ("a plan that is not archived should still match the code and the system map", "没归档的方案应和代码、系统图一致"),
    "PC_OVERLAP": ("packages %s and %s both list files under %s", "包 %s 和 %s 的可改文件重叠:%s"),
    "PC_DEP": ("package %s is in progress but its dependency %s is not merged", "包 %s 在做,但它依赖的 %s 还没合"),
    "PC_ROW": ("schedule row not recognized (%s); it is skipped", "排期这一行认不出(%s),已跳过"),
    "PC_ROW_COLS": ("%d cells, the header has %d", "%d 列,表头 %d 列"),
    "PC_ROW_STATUS": ("unknown status %r", "状态值 %r 不认识"),
    "PC_NODEP": ("package %s depends on %s, which is not in the schedule", "包 %s 依赖的 %s 不在排期里"),
    "PC_PATH": ("plan mentions %s, which does not exist", "方案提到的 %s 不存在"),
    "PC_SYSTEM": ("plan names system %s, which is not in systems", "方案头的系统 %s 不在 systems 里"),
}
messages.add(M)
RULES = [{"id": "C4", "level": "red", "what": "PC_C4", "why": "PC_C4_WHY"},
         {"id": "PL-STALE", "level": "yellow", "what": "PC_STALE", "why": "PC_STALE_WHY"}]


# ---------------------------------------------------------------- C4


def _cells(line):
    """Markdown 表格一行切成单元格。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]

def sched_path(cfg):
    return nm_config.docs_root(cfg) + "/schedule.md"


def schedule(snap, cfg):
    """总排期表 -> ([{pkg, deps, state, files: [glob], line}], [(行号, 原因)]);没有文件、没有表、没有“可改文件”列就是空。列数不对、状态值不认识的行跳过并记进第二项。"""
    text = snap.text(sched_path(cfg))
    if text is None:
        return [], []
    lines = text.replace("\r\n", "\n").split("\n")
    col = lambda cells, c: next((i for i, x in enumerate(cells) if code_of("sched_col", x) == c), None)
    for h, l in enumerate(lines):
        if not l.startswith("|"):
            continue
        cols = _cells(l)
        ip, ist, ifl, idep = (col(cols, c) for c in ("pkg", "status", "files", "deps"))
        if None in (ip, ist, ifl):
            continue
        out, bad = [], []
        for n, r in enumerate(lines[h + 2:], h + 3):
            if not r.startswith("|"):
                break
            c = _cells(r)
            if len(c) != len(cols):
                bad.append((n, t("PC_ROW_COLS", len(c), len(cols))))
                continue
            state = code_of("sched_status", c[ist])
            if not state:
                bad.append((n, t("PC_ROW_STATUS", c[ist])))
                continue
            files = [g.strip("` ") for g in pathglob.split_globs(re.sub(r"[、，;；\s]+", ",", c[ifl])) if g.strip("` ")]
            dep = [d for d in re.split(r"[,、，/\s]+", c[idep]) if d and not re.fullmatch(r"[-—–无]|none", d, re.I)] if idep is not None else []
            out.append({"pkg": c[ip], "deps": dep, "state": state, "files": files, "line": n})
        return out, bad
    return [], []


def _split(g):
    """glob -> [(字面前缀, 有没有通配符)],花括号先展开。"""
    out = []
    for x in pathglob.expand(g.lstrip("/")):
        m = WILD.search(x)
        out.append((x[:m.start()] if m else x, bool(m)))
    return out


def _near(a, b):
    """两个 (字面前缀, 通配符) 是否算重叠:都不带通配符按整条路径比;带的一边,前缀是另一边(前缀或整条路径)的前缀。"""
    (pa, wa), (pb, wb) = a, b
    if not wa and not wb:
        return pa == pb
    if wa and wb:
        return pa.startswith(pb) or pb.startswith(pa)
    return pa.startswith(pb) if wb else pb.startswith(pa)


def _clash(a, b, files):
    """两个包的 glob 列表重叠 -> (代表路径, 确定吗);不重叠返回 None。
    确定 = 有现存文件同时匹配两边(取排序第一个),或两边有字面路径完全相同;其余只是字面前缀推断(取更长的前缀)。"""
    ma, mb = pathglob.matcher(a), pathglob.matcher(b)
    both = sorted(p for p in files if ma(p) and mb(p))
    if both:
        return both[0], True
    xs = [y for g in a for y in _split(g)]
    ys = [z for g in b for z in _split(g)]
    same = sorted(x[0] for x in xs if not x[1] and x in ys)
    if same:
        return same[0], True
    for x in xs:
        for y in ys:
            if _near(x, y):
                return max(x[0], y[0], key=len), False
    return None


def c4(snap, cfg):
    sched = sched_path(cfg)
    pkgs, bad = schedule(snap, cfg)
    out, files, by = [], snap.files(), {q["pkg"]: q for q in pkgs}
    out += [F("yellow", "C4", sched, n, "row", t("PC_ROW", why), k=["row", str(n)]) for n, why in bad]
    for p in pkgs:
        for d in p["deps"]:
            if d not in by:
                out.append(F("yellow", "C4", sched, p["line"], "%s -> %s" % (p["pkg"], d), t("PC_NODEP", p["pkg"], d), k=[p["pkg"], d, "nodep"]))
        if p["state"] == "doing":
            for d in p["deps"]:
                if d in by and d != p["pkg"] and by[d]["state"] != "merged":
                    out.append(F("red", "C4", sched, p["line"], "%s -> %s" % (p["pkg"], d), t("PC_DEP", p["pkg"], d), k=[p["pkg"], d, ""]))
    for i, a in enumerate(pkgs):
        for b in pkgs[i + 1:]:
            if a["state"] == b["state"] and a["state"] in ("doing", "todo") and a["files"] and b["files"]:
                hit = _clash(a["files"], b["files"], files)
                if hit is not None:
                    path, sure = hit
                    x, y = sorted((a["pkg"], b["pkg"]))
                    out.append(F("red" if sure and a["state"] == "doing" else "yellow", "C4", sched, max(a["line"], b["line"]),
                                 "%s / %s %s" % (x, y, path), t("PC_OVERLAP", x, y, path), k=[x, y, path]))
    return out


# ---------------------------------------------------------------- PL-STALE

TICK = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)+$")  # 带斜杠、没有通配符和空格;最后一段要有扩展名(下面查)


def mentioned(text):
    """方案正文里反引号里的文件路径 [(行号, 路径)]:跳过代码围栏;带斜杠、最后一段有扩展名;去掉行号后缀 `:12`。"""
    lines = lessons.text_lines(text)
    out = []
    for n, (line, fenced) in enumerate(zip(lines, lessons.in_fence(lines)), 1):
        if fenced:
            continue
        for m in TICK.finditer(line):
            p = re.sub(r":\d+(?:-\d+)?$", "", m.group(1).strip())
            if PATHLIKE.match(p) and "." in posixpath.basename(p).strip("."):
                out.append((n, p))
    return out


def stale(snap, cfg, systems):
    out = []
    plans = nm_config.docs_root(cfg) + "/plans"
    tys = doctypes.types(nm_config.expanded(cfg))
    for rel in snap.ls(plans, ".md", True):
        if rel.startswith(plans + "/archive/") or doctypes.is_type_index(rel, doctypes.type_of(rel, tys), snap):  # 生成的索引页不查,免得叫 AI 去改它
            continue
        text = snap.text(rel)
        seen = set()
        for n, p in mentioned(text):
            if p not in seen and not snap.isfile(p):
                seen.add(p)
                out.append(F("yellow", "PL-STALE", rel, n, p, t("PC_PATH", p)))
        for s in [x for x in re.split(r"[,，、\s]+", doccheck.plan_head(text).get("systems", "")) if x]:
            if s not in systems:
                out.append(F("yellow", "PL-STALE", rel, 1, "system:" + s, t("PC_SYSTEM", s)))
    return out


def run(snap, changes, eff):
    on = eff.cfg["check"]["builtin"]
    systems = nm_map.systems_of(eff.cfg, deps.all_files(snap))[0] if "PL-STALE" in on else {}
    return (c4(snap, eff.cfg) if "C4" in on else []) + (stale(snap, eff.cfg, systems) if "PL-STALE" in on else [])
