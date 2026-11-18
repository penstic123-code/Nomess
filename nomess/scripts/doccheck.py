"""check 的内置文档检查(不用登记):系统说明页缺三行头 / docs 断链 / 新文件缺头注释 / 未核实教训 /
方案头(取代指向不存在的文件、归档方案缺状态)/ AGENTS.md 预算和 CLAUDE.md 导入 / 系统图首页预算。"""
import posixpath
import re
from urllib.parse import unquote

import deps
import lessons
import map as nm_map
import nm_config
from messages import NAMES, alts, code_of, name as nm_name, t
from nm_config import F, est_tokens

AGENTS_TOKENS = 1500  # AGENTS.md 整个文件的预算(官方建议 200 行内,细节放按路径的规则)
PLAN_HEAD_LINES = 12  # 方案头在文件开头这么多个非空行内


def _lines(snap, rel):
    return lessons.text_lines(snap.text(rel))


def system_pages(snap, cfg):
    names = list(cfg.get("systems", {}))
    names += [posixpath.splitext(posixpath.basename(p))[0] for p in snap.ls("docs/systems", ".md")]
    out = []
    for name in dict.fromkeys(names):
        rel = "docs/systems/%s.md" % name
        if not snap.isfile(rel):
            out.append(F("yellow", "DOC3", rel, 0, "missing", t("DOC3_NONE", name)))
            continue
        head = [l for l in _lines(snap, rel) if l.strip()][:12]
        miss = [c for c in NAMES["system_head"] if not any(re.match("(?:%s)[:：]" % "|".join(map(re.escape, alts("system_head", c))), l) for l in head)]
        if miss:
            out.append(F("yellow", "DOC3", rel, 1, "head", t("DOC3_HEAD", ":".join(nm_name("system_head", c) for c in miss))))
    return out


def dead_links(text, exists):
    """一段 md 文本里指向不存在的相对文件的链接:[(行号, 原文)];exists(相对该文件所在目录的路径) 说它存不存在。docs 断链(查快照)和记忆体检(查磁盘)共用这一份。
    认 ``` / ~~~ 围栏(围栏里不查)、<带空格的路径>、%20 之类的 URL 编码;去掉 ?查询 和 #锚点;http: 之类的外链和 / 开头的不查。"""
    out = []
    lines = lessons.text_lines(text)
    for i, (line, fenced) in enumerate(zip(lines, lessons.in_fence(lines)), 1):
        if fenced:
            continue
        for tgt in re.findall(r"\]\((<[^>]*>|[^)\s]+)", line):
            p = unquote(re.split(r"[#?]", tgt.strip("<>"))[0])
            if p and not p.startswith("/") and not re.match(r"[a-zA-Z][\w+.-]*:", p) \
                    and not exists(p):
                out.append((i, tgt))
    return out


def snap_exists(snap, rel):
    """exists 回调:相对 rel 所在目录的路径 p 在快照里是文件或目录。"""
    def exists(p):
        q = posixpath.normpath(posixpath.join(posixpath.dirname(rel), p))
        return snap.files().get(q) is not None or snap.isdir(q)
    return exists


def broken_links(snap):
    return [F("red", "DOC1", p, i, tgt, t("LINK_DEAD", tgt))
            for p in snap.ls("docs", ".md", True) for i, tgt in dead_links(snap.text(p), snap_exists(snap, p))]


def missing_headers(snap):
    return [F("yellow", "HDR", f, 1, "no header", t("HDR"))
            for f in deps.tracked(snap) if snap.read(f) and deps.header(snap, f) is None]


def unverified(snap, cfg):
    d = cfg.get("lessons_dir", "docs/lessons")
    n = sum(lessons.unverified_in(snap.text(p)) for p in snap.ls(d, ".md"))
    return [F("yellow", "L1", d, 0, "unverified", t("L1", n))] if n else []


def plan_head(text):
    """方案头 {status, supersedes, superseded_by: 值}(中英键都认,只含开头几行里有的;status 的值是代号 proposed / accepted / rejected / superseded,不认识的原样留)。"""
    keys = {w: c for c in NAMES["plan_head"] for w in alts("plan_head", c)}
    head = [l for l in lessons.text_lines(text) if l.strip()][:PLAN_HEAD_LINES]
    out = {}
    for l in head:
        m = re.match(r"(%s)[:：]\s*(.*)$" % "|".join(map(re.escape, keys)), l)
        if m:
            c, v = keys[m.group(1)], m.group(2).strip()
            out[c] = (code_of("plan_status", v) or v) if c == "status" else v
    return out


def plans(snap):
    """方案文件:docs/plans/ 下(含 archive/)的 .md。"""
    return snap.ls("docs/plans", ".md", True)


def plan_links(snap):
    """PLN1(红):方案头的“取代”“被取代”(NAMES["plan_head"] 里的 supersedes / superseded_by,其余键如“系统”不是文件)指向不存在的文件(相对方案文件所在目录)。"""
    out = []
    for rel in plans(snap):
        for k, v in plan_head(snap.text(rel)).items():
            if k in ("supersedes", "superseded_by") and v and not snap.isfile(posixpath.normpath(posixpath.join(posixpath.dirname(rel), v))):
                out.append(F("red", "PLN1", rel, 1, "%s %s" % (k, v), t("PLN1", nm_name("plan_head", k), v)))
    return out


def plan_status(snap):
    """PLN2(黄):归档方案缺状态;写了“被取代”而状态不是“已被取代”。"""
    out = []
    for rel in plans(snap):
        h = plan_head(snap.text(rel))
        if rel.startswith("docs/plans/archive/") and not h.get("status"):
            out.append(F("yellow", "PLN2", rel, 1, "no status", t("PLN2_NONE")))
        if h.get("superseded_by") and h.get("status") != "superseded":
            out.append(F("yellow", "PLN2", rel, 1, "superseded", t("PLN2_SUP")))
    return out


def agents(snap):
    """AGENTS1(黄):AGENTS.md 超预算;AGENTS2(黄):有 AGENTS.md 和 CLAUDE.md、但 CLAUDE.md 没有 @AGENTS.md 导入(Claude Code 有 CLAUDE.md 就不读 AGENTS.md)。"""
    out = []
    if not snap.isfile("AGENTS.md"):
        return out
    tok = est_tokens("\n".join(_lines(snap, "AGENTS.md")))
    if tok > AGENTS_TOKENS:
        out.append(F("yellow", "AGENTS1", "AGENTS.md", 0, "big", t("AGENTS1", tok, AGENTS_TOKENS)))
    if snap.isfile("CLAUDE.md") and not any(re.match(r"\s*@AGENTS\.md\s*$", l) for l in _lines(snap, "CLAUDE.md")):
        out.append(F("yellow", "AGENTS2", "CLAUDE.md", 0, "no import", t("AGENTS2")))
    return out


def map_index(snap, cfg):
    """MAP1(黄):系统图首页超预算(生成时已按固定顺序裁过,仍超说明别的部分太大)。"""
    rel = nm_map.OUT_DIR + "/index.md"
    if not snap.isfile(rel):
        return []
    budget, tok = cfg.get("map", {}).get("index_tokens", nm_map.INDEX_TOKENS), est_tokens("\n".join(_lines(snap, rel)))
    return [F("yellow", "MAP1", rel, 0, "big", t("MAP1", tok, budget))] if tok > budget else []


def red(snap):
    return broken_links(snap) + plan_links(snap)


def findings(snap, cfg):
    return (system_pages(snap, cfg) + red(snap) + missing_headers(snap) + unverified(snap, cfg)
            + plan_status(snap) + agents(snap) + map_index(snap, cfg))
