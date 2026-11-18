"""通用检查引擎。规则登记在 nomess.json 的 "check" 段,屎山检测由 DETECTORS 登记的模块提供;过了不出声(零输出,退出码 0),
有新红项、变坏或放宽退出码 1,配置错误退出 2。红 = 确定性错误,挡提交;黄 = 启发式/提示,只显示。
统一入口 evaluate(cand, base, ...):开关和颜色、allow、基线(nomess-baseline/2)、新增 / 变坏 / 存量、B1 / B2、去重都在这里做,
钩子、nomess check、--ci、review-input 只调它(接口说明见 scripts/README.md "检测器和模块")。
规则写法(id、level、what=查什么、why=防什么 必填):
  正则:  glob + forbid(匹配的行报) 或 require(匹配不到的文件报)
  命令:  cmd(列表,工作目录=仓库根;非零退出就报,取输出最后一行)
例外只走顶层 allow(rule + file | from+to + reason)。
另查(内置,不用登记):见 LEGACY 和 scripts/README.md。
--no-exec 不运行项目里的任何代码(跳过 cmd 规则和 cmd / py 生成器)。
--memory <目录> 做记忆体检(软预算、标题几乎相同只报黄,断链/目录超两级报红)。
"""
import importlib
import json
import math
import os
import re
import subprocess

import cache
import doccheck
import docgen
import lessons
import nm_config
import pathglob
import map as nm_map
import rules as nm_rules
import snapshot
from map import files_of
from messages import name as nm_name, t
from nm_config import BUILTIN, F, est_tokens

# 登记的检测器:一行一个模块名(带结尾逗号)。模块提供 RULES 和 run(snap, changes, eff),见 scripts/README.md。
DETECTORS = [
    # >>> P22 只在这两行之间追加
    # <<< P22
    # >>> P23 只在这两行之间追加
    "clones",
    "smells",
    # <<< P23
    # >>> P24 只在这两行之间追加
    "arch",
    # <<< P24
    # >>> P25 只在这两行之间追加
    "plancheck",
    # <<< P25
]
BASELINE = ".nomess-baseline.json"
BFORMAT = "nomess-baseline/2"
DIAG = frozenset({"CFG1", "BL1", "B1", "B2", "CMD1"})  # 诊断号:不进基线、不能写 allow
GATE_LEGACY = frozenset({"RUL1", "L5", "DOC1", "PLN1"})  # 钩子里跑的旧检查(都是红):和 P20 一致,不扩大
LEGACY = frozenset({"DOC1", "DOC3", "HDR", "L1", "L4", "L5", "RUL1", "RUL2", "RUL3", "RUL4", "RUL5",
                    "PLN1", "PLN2", "AGENTS1", "AGENTS2", "MAP1", "GEN", "M1", "M2", "M3", "M4", "M5", "M6", "M7"})
RESERVED = frozenset(BUILTIN) | LEGACY | DIAG
REVIEW_RANK = nm_config.REVIEW_LEVELS

SKIP_DIRS = {"archive", ".trash", ".git"}


def detectors():
    """按当前登记表导入(不另缓存,Python 的模块缓存够用;测试里 append 立即生效)。"""
    return [importlib.import_module(n) for n in DETECTORS]


def validate(rule):
    for k in ("id", "level", "what", "why"):
        if not rule.get(k):
            raise ValueError(t("RULE_MISSING", rule.get("id", "?"), k))
    if rule["level"] not in ("red", "yellow"):
        raise ValueError(t("RULE_LEVEL", rule["id"]))
    if sum(k in rule for k in ("forbid", "require", "cmd")) != 1:
        raise ValueError(t("RULE_KIND", rule["id"]))
    if "cmd" not in rule and "glob" not in rule:
        raise ValueError(t("RULE_GLOB", rule["id"]))
    if "glob" in rule:
        pathglob.check(rule["glob"])


def validate_rules(rules):
    for r in rules:
        validate(r)


def run_rule(snap, r, only=None):
    """only 给了就只查这些路径(提交钩子:只查和基准不同的文件);cmd 规则不受影响。基线键 = 文件(次数 = 文件里的命中数)。"""
    lvl, msg = r["level"], t("RULE_WHY", r["why"])
    if "cmd" in r:  # cmd 必须只检查、不改文件:提交钩子在它之后才决定报红,报红前没写东西只对 nomess 自己的生成物成立
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")  # Python 子进程输出 UTF-8;其他工具自己负责
        p = subprocess.run(r["cmd"], cwd=snap.root, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=r.get("timeout", 60))
        if p.returncode == 0:
            return []
        last = ((p.stdout + p.stderr).strip().splitlines() or [t("RULE_EXIT", p.returncode)])[-1]
        return [F(lvl, r["id"], "-", 0, last, "%s(%s)" % (r["what"], last), k=[last.strip()])]  # 不同失败不共用额度
    rx = re.compile(r["forbid"]) if "forbid" in r else None
    out = []
    for rel in files_of(snap, r["glob"]):
        if only is not None and rel not in only:
            continue
        text = snap.text(rel).replace("\r\n", "\n")  # 行尾的 \r 去掉:CRLF 文件里 ^X$ 照样匹配
        if rx:
            for i, line in enumerate(text.split("\n"), 1):
                if rx.search(line):
                    out.append(F(lvl, r["id"], rel, i, line, msg, k=[]))
        elif not re.search(r["require"], text, re.M):
            out.append(F(lvl, r["id"], rel, 1, "require " + r["require"], msg, k=[]))
    return out


def stale_sections(snap, cfg, exec_=True):
    """过时的生成段和系统图;exec_ 为假时不跑 cmd / py 生成器(不执行项目代码)。"""
    stale, _ = docgen.run(snap, cfg, exec_=exec_)
    out = [F("yellow", "GEN", f, 0, n, t("GEN_STALE", n)) for n, f in stale]
    if snap.isdir(nm_map.OUT_DIR):
        out += [F("yellow", "GEN", f, 0, f, t("MAP_STALE", f)) for f in nm_map.plan(snap, cfg)]
    return out


def _memory_index(d):
    return next((n for n in ("MEMORY.md", "INDEX.md") if os.path.isfile(os.path.join(d, n))), None)


def _page_titles(d, index):
    """{主题页文件名: 标题}:标题取索引里 [标题](文件) 的链接文字;索引没列的页用文件名(去 .md)。"""
    titles = {}
    with open(os.path.join(d, index), encoding="utf-8-sig", errors="replace") as f:
        for text, fn in re.findall(r"\[([^\]]+)\]\(<?([^)#>\s]+\.md)", f.read()):
            titles.setdefault(fn, text.strip())
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".md") and fn != index:
            titles.setdefault(fn, fn[:-3])
    return titles


def memory_check(d, cfg):
    """记忆目录体检:索引和主题页的软预算(黄)、目录超两级和断链(红)、未核实、标题几乎相同。阈值取 expanded(cfg)["memory"]。"""
    thr = nm_config.expanded(cfg)["memory"]
    out = []
    names = set()
    for root, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        names |= {os.path.splitext(f)[0] for f in fs if f.endswith(".md")}
    index = _memory_index(d)
    if index is None:
        return [F("red", "M1", d.replace("\\", "/"), 0, "no index", t("M1"))]
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        if root != d and files:
            rel = os.path.relpath(root, d).replace("\\", "/")
            out.append(F("red", "M4", rel, 0, rel, t("M4")))
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, d).replace("\\", "/")
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            tok = est_tokens(text)
            if rel == index:
                if tok > thr["index_tokens"]:
                    out.append(F("yellow", "M2", rel, 0, "index", t("M2", tok, thr["index_tokens"])))
            elif root == d and tok > thr["page_tokens"]:
                out.append(F("yellow", "M3", rel, 0, "big", t("M3_BIG", tok, thr["page_tokens"])))
            for i, line in enumerate(text.split("\n"), 1):
                for n in re.findall(r"\[\[([^\]|#]+)", line):
                    if n.strip() not in names:
                        out.append(F("red", "M5", rel, i, n, t("M5_WIKI", n.strip())))
            out += [F("red", "M5", rel, i, tgt, t("LINK_DEAD", tgt)) for i, tgt in doccheck.dead_links(text, lambda x, p=p: os.path.exists(os.path.join(os.path.dirname(p), x)))]
    un = lessons.count_unverified(d)
    if un:
        out.append(F("yellow", "M6", ".", 0, "unverified", t("M6", un)))
    titles = _page_titles(d, index)
    pages = [fn for fn in titles if os.path.isfile(os.path.join(d, fn))]
    for i, j in lessons.near_pairs([titles[fn] for fn in pages], thr["title_ratio"]):
        out.append(F("yellow", "M7", pages[i], 0, pages[j], t("M7", pages[j], titles[pages[i]], titles[pages[j]])))
    return out


def lesson_findings(snap, cfg, red_only):
    """教训库体检:红项(L5)总是查;red_only 为假时再加黄项(L4)。"""
    rel = cfg.get("lessons_dir", "docs/lessons")
    entries = lessons.snapshot_entries(snap, rel)
    out = lessons.red(entries, rel)
    return out if red_only else out + lessons.health(entries, rel, nm_config.expanded(cfg)["memory"]["title_ratio"])


# ---------------------------------------------------------------- 规则表

def rule_specs(exp, mods):
    """规则号 -> {kind, level, what, why, needs, select, freeze, cmd}。kind: builtin | legacy | diag | detector | project | relation。
    项目规则(check.rules、arch.relations)的号和保留号、检测器的号、彼此重复 -> 退出 2;检测器之间重号是程序错误。"""
    specs = {}
    for i in RESERVED:
        specs[i] = {"kind": "builtin" if i in BUILTIN else ("diag" if i in DIAG else "legacy"),
                    "select": "file", "freeze": i not in DIAG, "needs": None}
    det = set()
    for m in mods:
        for r in m.RULES:
            if r["id"] in det:
                raise ValueError("%s: rule id %s is registered by two detectors" % (m.__name__, r["id"]))
            det.add(r["id"])
            specs[r["id"]] = dict({"select": "file", "freeze": True, "needs": None}, **r, kind="detector")
    for kind, items in (("project", exp["check"]["rules"]), ("relation", exp["arch"]["relations"])):
        for r in items:
            rid = r.get("id")
            if rid in specs:
                raise ValueError(t("CFG_ID_DUP", rid))
            specs[rid] = {"kind": kind, "level": r.get("level"), "what": r.get("what"), "why": r.get("why"),
                          "select": "file", "freeze": True, "needs": None, "cmd": "cmd" in r}
    for n, a in enumerate(exp["allow"]):
        s = specs.get(a["rule"])
        if s is None or not s["freeze"] or s.get("cmd") or s["select"] != ("edge" if "from" in a else "file"):
            raise ValueError(t("ALLOW_BAD", n, a["rule"]))
    return specs


def enabled(rid, exp, specs):
    """这个号在展开后的配置 exp 里算不算启用(首次冻结资格、--freeze、--rules 用)。exp 为 None = 没有配置。"""
    if exp is None:
        return False
    if rid in BUILTIN:
        return rid in exp["check"]["builtin"] or any(rid in s.get("checks", {}).get("add", []) for s in exp["scopes"])
    s = specs.get(rid)
    if s is None:
        return False
    if s["kind"] in ("project", "relation"):
        return any(r.get("id") == rid for r in exp["check"]["rules"] + exp["arch"]["relations"])
    return bool(s["needs"](exp)) if s["needs"] else True


# ---------------------------------------------------------------- 观测

def _setup(cfg):
    """配置 -> (检测器模块, Effective, 规则表);规则号唯一、allow 合法、规则写法都在这里查(不对退出 2)。"""
    mods = detectors()
    eff = nm_config.Effective(cfg)
    specs = rule_specs(eff.cfg, mods)
    validate_rules(eff.cfg["check"]["rules"])
    return mods, eff, specs


def full_changes(cand, eff):
    """全量检查的 changes:快照里的普通文件(不含符号链接、子模块)全部算 A;每个文件问一次有效配置,scope 冲突在这里暴露。"""
    out = {}
    for p, m in cand.files().items():
        if m in snapshot.REGULAR:
            eff(p)
            out[p] = "A"
    return out


def _worktree_dirty(root):
    """已跟踪文件的工作区和索引不一致(沿用环境里的 GIT_INDEX_FILE;不看未跟踪文件)。"""
    return subprocess.run(["git", "diff", "--quiet"], cwd=root, capture_output=True).returncode != 0


def _checked(name, fs):
    """一个来源的发现:指标值要是有限数;同一身份只能有一条指标,不能次数和指标混用。错了是程序错误,带来源名。"""
    kinds = {}
    for f in fs:
        m = f["metric"]
        if m is not None and (isinstance(m, bool) or not isinstance(m, (int, float)) or not math.isfinite(m)):
            raise ValueError("%s: rule %s: bad metric %r" % (name, f["rule"], m))
        key = (f["rule"], _ident(f, f["level"]))
        kind = "n" if m is None else "v"
        if key in kinds and (kind == "v" or kinds[key] != kind):
            raise ValueError("%s: rule %s: baseline key %s has several metrics or mixes counts and metrics" % (name, f["rule"], _show(key[1])))
        kinds[key] = kind
    return fs


def observe(cand, cfg, eff, specs, mods, changes, only, gate, exec_cmd):
    """跑检测并按开关定色 -> (观测, 本轮真正启用并检查过的规则号)。观测已过开关、没过 allow;每条多 sev(原始颜色)。
    gate(钩子):旧检查只跑可能变红的(顶层红,或某条 scope 把它升红);cmd 规则只在已跟踪文件的工作区和索引一致时跑,
    否则跳过并报黄 CMD1(它读的是工作区,和待检的索引对不上,交给 CI)。"""
    def may_be_red(rid, level):
        return level == "red" or any(sc.get("level", {}).get(rid) == "red" for sc in eff.cfg["scopes"])
    raw, ran = [], set()
    cmd_ok = None  # 第一条要跑的 cmd 规则才去问 git(没有 cmd 规则就不起这个子进程)
    skipped = []
    for r in eff.cfg["check"]["rules"]:
        if gate and not may_be_red(r["id"], r["level"]) or "cmd" in r and not exec_cmd:
            continue
        if "cmd" in r and cmd_ok is None:
            cmd_ok = not (gate and _worktree_dirty(cand.root))
        if "cmd" in r and not cmd_ok:
            skipped.append(r["id"])
            continue
        raw += run_rule(cand, r, only)
        ran.add(r["id"])
    legacy = nm_rules.broken_frontmatter(cand) + lesson_findings(cand, cfg, gate)
    hdr = enabled("HDR", eff.cfg, specs)
    if gate:
        legacy += doccheck.red(cand)
        ran |= GATE_LEGACY
        if hdr and may_be_red("HDR", "yellow"):
            legacy += doccheck.missing_headers(cand)
            ran.add("HDR")
    else:
        legacy += doccheck.findings(cand, cfg) + nm_rules.findings(cand, cfg) + stale_sections(cand, cfg, exec_cmd)
        ran |= {i for i in LEGACY if not i.startswith("M") and (i != "HDR" or hdr)} - (set() if exec_cmd else {"GEN"})
    raw = _checked("check", raw) + _checked("check", legacy)
    for m in mods:
        raw += _checked(m.__name__, m.run(cand, changes, eff))
        ran |= {r["id"] for r in m.RULES if enabled(r["id"], eff.cfg, specs)}
        if getattr(m, "RELATIONS", False):  # 声明:这个模块负责 arch.relations 的动态号
            ran |= {r["id"] for r in eff.cfg["arch"]["relations"]}
    file_ids = {i for i, c in BUILTIN.items() if c == "file"} | {r["id"] for r in eff.cfg["check"]["rules"] if "cmd" not in r}
    out = []
    for f in raw:
        r = f["rule"]
        f["sev"] = f["level"]
        if BUILTIN.get(r) == "tree":
            if r not in eff.cfg["check"]["builtin"]:
                continue
        elif r in file_ids:  # 按文件的号:file 和 also 各看自己的有效配置,任一边开着就留,颜色取开着的几边里最严的
            on = [x for x in [f["file"]] + f["also"] if x != "-" and r in eff(x)["checks"]]
            if not on:
                continue
            f["level"] = "red" if any(eff(x)["level"].get(r, f["sev"]) == "red" for x in on) else "yellow"
        out.append(f)
    if skipped:
        out.append(_diag(F("yellow", "CMD1", "-", 0, ",".join(skipped), t("CMD1", ", ".join(skipped)), k=[])))
    return out, ran


def _ident(f, level):
    return level, tuple(sorted(p for p in [f["file"]] + f["also"] if p != "-")), tuple(f["k"])


def ident(f):
    """基线身份:(原始颜色, 排好序的路径, k)。颜色在身份里:黄的额度抵不了红。"""
    return _ident(f, f["sev"])


def tally(obs):
    """观测 -> {(规则号, 身份): ("n", 次数) | ("v", 指标)}(唯一性已在 _checked 查过)。诊断号不算。"""
    out = {}
    for f in obs:
        if f["rule"] in DIAG:
            continue
        key = (f["rule"], ident(f))
        out[key] = ("n", out.get(key, ("n", 0))[1] + 1) if f["metric"] is None else ("v", f["metric"])
    return out


# ---------------------------------------------------------------- 基线(nomess-baseline/2)

ENTRY_KEYS = frozenset({"file", "also", "k", "level", "n", "v"})


def _no_dup_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key in %s" % keys)
    return dict(pairs)


def load_baseline(snap, cfg, specs=None):
    """快照里的基线 -> {规则号: {身份: ("n" | "v", 数)}};没有文件为空。严格解析,不合格退出 2:重复字段、多余字段、
    file 为 "-" 却有 also、数值不合法、同号下身份重复;给了规则表时,freeze 为 False 的号有条目也算不合格。"""
    path = nm_config.expanded(cfg)["check"]["baseline"]
    text = snap.text(path)
    if text is None:
        return {}
    try:
        d = json.loads(text, object_pairs_hook=_no_dup_keys)
    except ValueError as e:
        raise ValueError(t("BASELINE_BAD", path, "-", e) if "duplicate key" in str(e) else t("BASELINE_OLD", path))
    if not isinstance(d, dict) or d.get("format") != BFORMAT or not isinstance(d.get("rules"), dict):
        raise ValueError(t("BASELINE_OLD", path))
    out = {}
    for rid, entries in d["rules"].items():
        if not isinstance(entries, list) or (entries and specs and rid in specs and not specs[rid]["freeze"]):
            raise ValueError(t("BASELINE_BAD", path, rid, entries))
        b = out[rid] = {}
        for e in entries:
            ok = isinstance(e, dict) and isinstance(e.get("file"), str) and isinstance(e.get("also", []), list) \
                and isinstance(e.get("k"), list) and all(isinstance(x, str) for x in e.get("also", []) + e.get("k", [])) \
                and e.get("level") in ("red", "yellow") and ("n" in e) != ("v" in e) and not set(e) - ENTRY_KEYS \
                and not (e["file"] == "-" and e.get("also"))
            num = e.get("n", e.get("v")) if ok else None
            if ok and "n" in e:
                ok = isinstance(num, int) and not isinstance(num, bool) and num >= 0
            elif ok:
                ok = isinstance(num, (int, float)) and not isinstance(num, bool) and math.isfinite(num)
            if not ok:
                raise ValueError(t("BASELINE_BAD", path, rid, e))
            paths = [nm_config.repo_path(p, path, rid) for p in ([] if e["file"] == "-" else [e["file"]]) + e.get("also", [])]
            idt = (e["level"], tuple(sorted(paths)), tuple(e["k"]))
            if idt in b:
                raise ValueError(t("BASELINE_BAD", path, rid, e))
            b[idt] = ("n" if "n" in e else "v", num)
    return out


def dump_baseline(B):
    """基线 -> 文本:一行一个条目,规则号和条目都排序,两次生成逐字节相同;冻结过、没有命中的号写空列表。"""
    blocks = []
    for rid in sorted(B):
        ents = []
        for (lv, paths, k), (kind, num) in sorted(B[rid].items(), key=lambda x: (x[0][1], x[0][2], x[0][0])):
            e = {"file": paths[0] if paths else "-"}
            if len(paths) > 1:
                e["also"] = list(paths[1:])
            e.update(k=list(k), level=lv)
            e[kind] = num
            ents.append("   " + json.dumps(e, ensure_ascii=False))
        blocks.append("  %s: [%s]" % (json.dumps(rid, ensure_ascii=False), "\n" + ",\n".join(ents) + "\n  " if ents else ""))
    return '{"format": "%s",\n "rules": {\n%s}}\n' % (BFORMAT, ",\n".join(blocks) + ("\n" if blocks else ""))


def renamed(B, inv):
    """把基线里的旧路径换成新路径(inv: {旧: 新}),重新排序;撞到同一身份的合并:次数相加,指标取大。"""
    if not inv:
        return B
    out = {}
    for rid, ents in B.items():
        b = out[rid] = {}
        for (lv, paths, k), (kind, num) in ents.items():
            idt = (lv, tuple(sorted(inv.get(p, p) for p in paths)), k)
            if idt in b and b[idt][0] == kind:
                num = num + b[idt][1] if kind == "n" else max(num, b[idt][1])
            b[idt] = (kind, num)
    return out


def _show(idt):
    lv, paths, k = idt
    return " ".join(list(paths) + list(k)) or "-"


def rebaseline(cand, base, mode, exec_cmd):
    """--freeze / --tighten:全量观测(没过 allow)-> (新基线文本, 条数, 基线路径)。base 是 HEAD 的树(没有提交为 None),
    用来把基线跟着改名走。freeze 只给还没有、本轮启用并检查过、允许冻结的号写条目;tighten 只动本轮检查过的号,
    删掉观测不到的身份,数只降不升。"""
    cfg = nm_config.load_snapshot(cand)
    if cfg is None:
        raise ValueError(t("NO_CONFIG", cand.root))
    mods, eff, specs = _setup(cfg)
    obs, ran = observe(cand, cfg, eff, specs, mods, full_changes(cand, eff), None, False, exec_cmd)
    inv = {o: n for n, o in cand.renames(base).items()}
    seen, B, n = tally(obs), renamed(load_baseline(cand, cfg, specs), inv), 0
    for rid in sorted(ran):
        s = specs.get(rid)
        if mode == "freeze" and rid not in B and s and s["freeze"]:
            B[rid] = {idt: v for (r, idt), v in seen.items() if r == rid}
            n += len(B[rid])
        elif mode == "tighten" and rid in B:
            B[rid] = {idt: (kind, min(num, seen[(rid, idt)][1])) for idt, (kind, num) in B[rid].items()
                      if seen.get((rid, idt), ("",))[0] == kind}
            n += len(B[rid])
    return dump_baseline(B), n, eff.cfg["check"]["baseline"]


# ---------------------------------------------------------------- 统一入口

def _loosen(color_red, rule, file, msg):
    f = F("red" if color_red else "yellow", rule, file, 0, msg, msg, k=[])
    f.update(sev=f["level"], state="loosen", frozen=False)
    return f


def _diag(f):
    f.update(sev=f["level"], state="new", frozen=False)
    return f


def evaluate(cand, base, *, exec_cmd, gate=False, full=False, allow_loosen=False):
    """对待检快照 cand 相对基准快照 base(None = 还没有提交)做全部检查,返回分好类的结果(形状固定):
    {skipped, findings(每条带 state: new | worse | grew | frozen | loosen), new_allow, new_frozen, review, writes}。
    exec_cmd:跑不跑 cmd 规则和 cmd / py 生成器;gate:钩子(旧检查只跑红级,见 GATE_LEGACY);full:按文件的检测全树查
    (手动 check);allow_loosen:人批准过放宽(--ci --allow-loosen),以 cand 的基线为准,B1 / B2 降黄。配置错误抛 ValueError(退出 2)。"""
    res = {"skipped": None, "findings": [], "new_allow": [], "new_frozen": [], "review": None, "writes": {}}
    btext = base.text(nm_config.CONFIG_NAME) if base is not None else None
    text = cand.text(nm_config.CONFIG_NAME)
    if text is None and btext is None:
        res["skipped"] = t("CHK_SKIP")
        return res
    bcfg = nm_config.parse(btext, nm_config.CONFIG_NAME) if btext is not None else None
    if text is None:  # 基准有、这里删了:放宽
        res["findings"].append(_loosen(not allow_loosen, "B2", nm_config.CONFIG_NAME, t("B2_GONE")))
        return res
    cfg = nm_config.parse(text, nm_config.CONFIG_NAME)  # 最后解析 cand:提示语按它的 lang
    mods, eff, specs = _setup(cfg)
    bexp = nm_config.expanded(bcfg) if bcfg else None
    bspecs = rule_specs(bexp, mods) if bexp else {}
    bpath = eff.cfg["check"]["baseline"]
    inv = {o: n for n, o in cand.renames(base).items()}
    # 基准里不认识的号(当时没登记)不算额度;待检里不认识的号保留、报 BL1,也不算额度
    Bb = {r: v for r, v in renamed(load_baseline(base, bcfg, bspecs), inv).items() if r in bspecs} if bcfg else {}
    Bn0 = load_baseline(cand, cfg, specs)
    Bn = renamed(Bn0, inv)
    newids = sorted(r for r in Bn if r in specs and r not in Bb)
    diff = cand.diff(base)
    full = full or bexp != eff.cfg or bool(newids)
    changes = full_changes(cand, eff) if full else diff
    obs, ran = observe(cand, cfg, eff, specs, mods, changes, None if full else {p for p, s in diff.items() if s != "D"}, gate, exec_cmd)

    # 首次冻结:只给基准里没启用、待检里已登记、已启用、允许冻结、本轮检查过的号,条目逐条对本次全量观测;
    # 已有的号多出身份或数变大 -> B1
    seen, loose, judge = tally(obs), [], {r: dict(v) for r, v in Bb.items() if r in specs}
    for rid in newids:
        in_base = enabled(rid, bexp, specs)
        ok = not in_base and specs[rid]["freeze"] and rid in ran
        judge[rid] = {}
        for idt, (kind, num) in sorted(Bn[rid].items()):
            got = seen.get((rid, idt))
            if not ok or got is None or got[0] != kind or num > got[1]:
                loose.append(("B1", bpath, t("B1_FIRST", rid, _show(idt)) if in_base else t("B1_KEY", rid, _show(idt), num)))
            else:
                judge[rid][idt] = (kind, num)
    for rid in sorted(set(Bn) & set(Bb)):
        for idt, (kind, num) in sorted(Bn[rid].items()):
            old = Bb[rid].get(idt)
            if old is None or old[0] != kind or num > old[1]:
                loose.append(("B1", bpath, t("B1_KEY", rid, _show(idt), num)))
    if bexp is not None:
        loose += [("B2", nm_config.CONFIG_NAME, t("B2_CFG", path, d)) for path, d in nm_config.loosened(bexp, eff.cfg)]
    if allow_loosen:
        judge = {r: v for r, v in Bn.items() if r in specs}

    # allow:命中的去掉(仍留在观测里);D1 两边任一文件匹配都算
    allow = [(a, pathglob.matcher([a["file"]]) if "file" in a else None) for a in eff.cfg["allow"]]

    def allowed(f):
        for a, m in allow:
            if a["rule"] == f["rule"] and (any(m(x) for x in [f["file"]] + f["also"] if x != "-") if m else
                                           f["edge"] is not None and tuple(f["edge"]) == (a["from"], a["to"])):
                return True
        return False
    kept = [f for f in obs if not allowed(f)]

    # 定状态:次数类按行序前面的算存量;指标类按 grow_slack(取 file 那一边)
    groups = {}
    for f in kept:
        if f["rule"] not in DIAG:
            groups.setdefault((f["rule"], ident(f)), []).append(f)
    for (rid, idt), fs in groups.items():
        b = judge.get(rid, {}).get(idt)
        if fs[0]["metric"] is not None:
            f, v = fs[0], fs[0]["metric"]
            slack = (eff(f["file"])["smells"] if f["file"] != "-" else eff.cfg["smells"])["grow_slack"]
            f["state"] = "new" if b is None or b[0] != "v" else "worse" if v > b[1] * (1 + slack) else "grew" if v > b[1] else "frozen"
        else:
            nb = b[1] if b and b[0] == "n" else 0
            for i, f in enumerate(sorted(fs, key=lambda x: x["line"])):
                f["state"] = "frozen" if i < nb else "new"
    for f in kept:
        if f["rule"] in DIAG:
            continue
        if f["state"] in ("frozen", "grew"):
            f["level"] = "yellow"
        f["frozen"] = f["state"] == "frozen"

    # 去重:under 指向的那条会挡提交(红、没豁免、不是存量)时本条不报
    block = {(f["rule"], tuple(f["k"])) for f in kept if f["level"] == "red" and f["state"] != "frozen"}
    kept = [f for f in kept if not (f["under"] and (f["under"][0], tuple(f["under"][1])) in block)]

    res["findings"] = kept + [_loosen(not allow_loosen, r, file, msg) for r, file, msg in loose]
    res["findings"] += [_diag(F("yellow", "BL1", bpath, 0, rid, t("BL1", rid), k=[])) for rid in sorted(Bn) if rid not in specs]
    if not gate:
        res["findings"] += [_diag(f) for f in nm_config.unknown_keys(cfg)]
    if Bn != Bn0:  # 基线跟着改名走:钩子把它写回这次提交
        res["writes"][bpath] = dump_baseline(Bn).encode("utf-8")
    old_allow = {json.dumps(a, sort_keys=True, ensure_ascii=False) for a in (bexp or {}).get("allow", [])}
    res["new_allow"] = [a for a in eff.cfg["allow"] if json.dumps(a, sort_keys=True, ensure_ascii=False) not in old_allow]
    res["new_frozen"] = newids
    if diff:
        rank = REVIEW_RANK.index
        p = max(sorted(diff), key=lambda x: rank(eff(x)["review"]))
        res["review"] = {"level": eff(p)["review"], "file": p}
    return res


def blocking(res):
    """挡不挡:有没有红(只有 new、worse、loosen 可能是红)。"""
    return any(f["level"] == "red" for f in res["findings"])


def report(findings, show_all, as_json=False, red_only=False):
    """终端:存量只计数(--all 逐条列,标“存量”);全是存量时不出声。--json:全部逐条,每项多 state、frozen。"""
    for f in findings:
        f.setdefault("state", "new")
        f.setdefault("frozen", False)
    if red_only:
        findings = [f for f in findings if f["level"] == "red"]
    findings.sort(key=lambda f: (f["frozen"], f["level"] != "red", f["rule"], f["file"], f["line"]))
    red = sum(f["level"] == "red" for f in findings)
    if as_json:
        print(json.dumps([{k: f[k] for k in ("level", "rule", "file", "line", "msg", "state", "frozen")} for f in findings],
                         ensure_ascii=False))
        return 1 if red else 0
    live = [f for f in findings if not f["frozen"]]
    if not findings or not (live or show_all):
        return 0
    shown = findings if show_all else live[:5]
    for f in shown:
        print("%s %s %s%s %s%s" % (nm_name("level", f["level"]), f["rule"], f["file"], ":%d" % f["line"] if f["line"] else "", f["msg"],
                                   " " + t("FROZEN_TAG") if f["frozen"] else ""))
    print(t("SUMMARY", red, len(live) - red, len(findings) - len(live), "" if len(shown) == len(findings) else t("ALL_HINT")))
    return 1 if red else 0


def _rev(root, ref):
    p = subprocess.run(["git", "rev-parse", "--verify", "-q", ref + "^{commit}"], cwd=root, capture_output=True, text=True)
    if p.returncode:
        raise ValueError("git rev-parse %s: not a commit" % ref)
    return p.stdout.strip()


def _ci(a):
    """nomess check --ci --base X:直接从 git 顶层读两棵树(不靠工作区里的配置);工作区要和 HEAD 一致(cmd 规则在工作区跑);
    不读检出目录里的缓存;待检提交的基线没跟着改名规范化 -> 红(要走钩子提交,或手动 --freeze 后再提交)。"""
    if a.freeze or a.tighten or a.rules or a.no_exec or a.memory:
        raise ValueError(t("CI_EXCLUSIVE"))
    if not a.base:
        raise ValueError(t("CI_NEED_BASE"))
    root = snapshot.toplevel(os.getcwd())
    if subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True).stdout.strip():
        raise ValueError(t("CI_DIRTY"))
    cache.disable_read()
    head, b = _rev(root, "HEAD"), _rev(root, a.base)
    if head == b:
        print(t("CI_SAME"))
        return 0
    with snapshot.open_snapshot(root, "tree", head) as cand, snapshot.open_snapshot(root, "tree", b) as base:
        res = evaluate(cand, base, exec_cmd=True, allow_loosen=a.allow_loosen)
    if res["skipped"]:
        print(res["skipped"])
        return 0
    res["findings"] += [_loosen(True, "B1", rel, t("CI_RENAME", rel)) for rel in res["writes"]]
    return report(res["findings"], a.all, a.json)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess check", description="general check engine: rules in nomess.json, registered detectors, built-in doc checks, ratchet")
    ap.add_argument("--freeze", action="store_true", help="write baseline entries for enabled rule ids that have none yet (first freeze)")
    ap.add_argument("--tighten", action="store_true", help="drop baseline entries that no longer occur and lower counts; never raises")
    ap.add_argument("--red", action="store_true", help="what the commit hook runs; print red findings only")
    ap.add_argument("--all", action="store_true", help="do not truncate the output; list frozen findings too")
    ap.add_argument("--no-exec", dest="no_exec", action="store_true",
                    help="run no project code: skip cmd rules and cmd / py doc generators (for read-only reviews)")
    ap.add_argument("--json", action="store_true",
                    help="print a JSON array, each item level / rule / file / line / msg / state / frozen (for the extension)")
    ap.add_argument("--rules", action="store_true", help="list the rules: id, level, what it checks / what it prevents")
    ap.add_argument("--ci", action="store_true", help="check the HEAD commit against --base (CI)")
    ap.add_argument("--base", metavar="SHA", help="with --ci: the trusted base commit (PR base or push before)")
    ap.add_argument("--allow-loosen", dest="allow_loosen", action="store_true",
                    help="with --ci: a person approved loosening; judge by the checked commit's baseline, B1 / B2 become yellow")
    ap.add_argument("--memory", metavar="DIR", help="memory health check")
    a = ap.parse_args(argv)
    if a.ci:
        return _ci(a)
    try:
        config = nm_config.find_config()
        cfg = nm_config.load(config)
    except FileNotFoundError:
        if not a.memory:
            raise
        config, cfg = None, {}
    if a.memory:
        return report(memory_check(a.memory, cfg), a.all, a.json)
    root = os.path.dirname(config)
    exec_cmd = not a.no_exec
    if a.rules:
        exp = nm_config.expanded(cfg)
        validate_rules(exp["check"]["rules"])
        for r in exp["check"]["rules"] + exp["arch"]["relations"]:
            print(t("RULES_LINE", r["id"], r["level"], r["what"], r["why"]))
        for m in detectors():
            specs = rule_specs(exp, [m])
            for r in m.RULES:
                print(t("RULES_LINE", r["id"], r["level"], t(r["what"]), t(r["why"])) + ("" if enabled(r["id"], exp, specs) else t("RULES_OFF")))
        return 0
    if a.freeze or a.tighten:
        with snapshot.open_snapshot(root, "worktree") as snap:
            base = snapshot.open_snapshot(root, "tree", "HEAD") if snapshot.has_commit(root, "HEAD") else None
            try:
                text, n, bp = rebaseline(snap, base, "freeze" if a.freeze else "tighten", exec_cmd)
            finally:
                if base is not None:
                    base.close()
        target = os.path.realpath(os.path.join(root, bp))
        if os.path.commonpath([os.path.realpath(root), target]) != os.path.realpath(root):
            raise ValueError(t("BAD_PATH", nm_config.CONFIG_NAME, "check.baseline", bp))
        nm_config.no_link(root, bp)
        nm_config.atomic_write(os.path.join(root, bp), text)
        print(t("FROZEN", n, bp) if a.freeze else t("TIGHTENED", bp))
        return 0
    with snapshot.open_snapshot(root, "worktree") as cand:
        base = snapshot.open_snapshot(root, "tree", "HEAD") if snapshot.has_commit(root, "HEAD") else None
        try:
            res = evaluate(cand, base, exec_cmd=exec_cmd, gate=a.red, full=True)
        finally:
            if base is not None:
                base.close()
    if res["skipped"]:
        print(res["skipped"])
        return 0
    return report(res["findings"], a.all, a.json, a.red)
