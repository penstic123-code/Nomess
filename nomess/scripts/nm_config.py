"""nomess.json 的查找与读取(各子命令共用)。路径都相对 nomess.json 所在目录。"""
import copy
import difflib
import glob
import json
import os
import posixpath
import re
import shutil
import tempfile

import pathglob
from messages import t, set_lang

CONFIG_NAME = "nomess.json"
FORMAT = "nomess/1"
REVIEW_LEVELS = ("off", "light", "standard", "strict")


def find_config(start=None):
    """从 start 往上找 nomess.json,停在仓库顶层(有 .git 的那一层:目录、worktree 或子模块的文件),不往父目录找。"""
    d = os.path.abspath(start or os.getcwd())
    while True:
        p = os.path.join(d, CONFIG_NAME)
        if os.path.isfile(p):
            return p
        up = os.path.dirname(d)
        if up == d or os.path.exists(os.path.join(d, ".git")):
            raise FileNotFoundError(t("NO_CONFIG", start or os.getcwd()))
        d = up


def load(path):
    with open(path, encoding="utf-8-sig") as f:  # 兼容 PowerShell 5.1 写出的 BOM;本脚本写出一律无 BOM
        return parse(f.read(), path)


def load_snapshot(snap):
    """快照根目录的 nomess.json;没有返回 None。配置只认仓库顶层。"""
    text = snap.text(CONFIG_NAME)
    return None if text is None else parse(text, CONFIG_NAME)


def parse(text, path):
    cfg = json.loads(text.lstrip("﻿"))
    set_lang(cfg.get("lang", "en"))  # 提示语的语言;全进程一份,各模块的 t() 读它
    if cfg.get("format") != FORMAT:
        raise ValueError(t("BAD_FORMAT", path, FORMAT))
    mb = cfg.get("main_branch")
    if not isinstance(mb, str) or not mb:
        raise ValueError(t("NO_MAIN", path))
    level = cfg.get("review", {}).get("level", "standard")
    if level not in REVIEW_LEVELS:
        raise ValueError(t("BAD_LEVEL", path, " / ".join(REVIEW_LEVELS)))
    _validate(cfg, path)
    for name, globs in cfg.get("systems", {}).items():
        if not isinstance(globs, list) or not globs or not all(isinstance(g, str) and g.strip() for g in globs):
            raise ValueError(t("BAD_SYSTEMS", path, name))
        for g in globs:
            pathglob.check(g)
    for key, kind in (("map", "index_tokens"), ("rules", "file_tokens")):
        v = cfg.get(key, {}).get(kind, 1)
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ValueError(t("BAD_BUDGET", path, key, kind))
    # 路径类值统一成仓库相对、正斜杠、无 ./ 和结尾斜杠;各模块直接拿来查快照和拼磁盘路径
    if "lessons_dir" in cfg:
        cfg["lessons_dir"] = repo_path(cfg["lessons_dir"], path, "lessons_dir")
    if "baseline" in cfg.get("check", {}):
        cfg["check"]["baseline"] = repo_path(cfg["check"]["baseline"], path, "check.baseline")
    for name, spec in cfg.get("docgen", {}).items():
        if "file" in spec:
            spec["file"] = repo_path(spec["file"], path, "docgen.%s.file" % name)
    return cfg


def _rooted(p):
    """带盘符、以 / 或 \\ 开头、含 NUL:不是仓库内的相对路径。"""
    return "\0" in p or bool(re.match(r"[A-Za-z]:", p)) or p.startswith(("/", "\\"))


def repo_path(v, path, key):
    """配置里的路径 -> 仓库相对的规范写法;空、盘符、开头的 / 或 \\、NUL、越出仓库都报配置错误。
    规范化前后都查(C:/../docs/x.md 规范化后不带盘符;a/../C:/x 规范化后才露出盘符)。"""
    if not isinstance(v, str) or not v.strip() or _rooted(v):
        raise ValueError(t("BAD_PATH", path, key, v))
    p = posixpath.normpath(v.replace("\\", "/"))
    if p in (".", "..") or p.startswith("../") or _rooted(p):
        raise ValueError(t("BAD_PATH", path, key, v))
    return p


def F(level, rule, file, line, text, msg, *, k=None, also=(), metric=None, edge=None, under=None):
    """一条检查发现(检测器和内置检查共用)。level: 原始颜色 red | yellow;file: 仓库相对路径或 "-";line 只用于显示。
    k: 基线键里路径以外的部分(字符串列表,缺省 [text]);路径只放 file / also(改名映射只改这两处)。
    also: 和 file 对称的另一边文件(D1);metric: 指标值(有就是指标类,按 grow_slack 判);
    edge: (from, to) 子系统名,select 为 edge 的号必填;under: (规则号, k),那条发现会挡提交时本条不报。"""
    text = " ".join(text.split())
    return {"level": level, "rule": rule, "file": file, "line": line, "text": text, "msg": msg,
            "k": [text] if k is None else list(k), "also": list(also), "metric": metric, "edge": edge, "under": under}


# ---------------------------------------------------------------- 缺省表、有效配置、放宽判定(P21)

SIZES = ("small", "medium", "large")
# check.builtin 的词表:号 -> file(按文件,scopes 能开关、改色)| tree(按整棵树,只认顶层)
BUILTIN = {"D1": "file", "P1": "file", "P2": "file", "P5": "file", "S1": "file", "S2": "file", "HDR": "file",
           "A1": "tree", "C4": "tree", "PL-DUP": "tree", "PL-STALE": "tree"}
SIZE = {"small": {"builtin": ["D1", "P1", "S1"], "review": "light"},
        "medium": {"builtin": ["A1", "D1", "P1", "S1"], "review": "standard"},
        "large": {"builtin": ["A1", "C4", "D1", "P1", "PL-DUP", "PL-STALE", "S1"], "review": "standard"}}
# 缺省表 = 合法键表:字典逐层比;"*" 是名字随用户取的那一层的条目样子(只用于认键,展开时不往用户条目里补)。
# 列表条目的键见 ITEM_KEYS。路径类(加载时规范化):check.baseline、lessons_dir、docgen.*.file;glob 类:check.rules[].glob、
# scopes[].paths、allow[].file、systems.*、map.*.glob
DEFAULTS = {
    "format": None, "main_branch": None,  # 必填,parse 查
    "size": "small",  # 给 size 出现之前写的配置用,开的检查最少;init 一定会写
    "lang": "en",
    "check": {"rules": [], "baseline": ".nomess-baseline.json", "builtin": None},  # builtin None = 跟 size
    "smells": {
        "file_lines": 800, "func_lines": 80, "clone_tokens": 100, "clone_lines": 8, "doc_clone_tokens": 60,
        "grow_slack": 0.1, "fan_in": 15, "extra_ext": [],
        # >>> P22 只在这两行之间追加
        # <<< P22
        # >>> P23 只在这两行之间追加
        # <<< P23
        # >>> P25 只在这两行之间追加
        # <<< P25
    },
    "scopes": [],
    "allow": [],
    "arch": {
        "layers": [], "independent": [], "forbid": [], "relations": [],
        # >>> P24 只在这两行之间追加
        # <<< P24
    },
    "systems": {"*": []},
    "docgen": {"*": {"file": None, "map": None, "cmd": None, "py": None, "builtin": None, "timeout": None, "dir": None}},
    "map": {"index_tokens": 1500, "page_tokens": 8000,
            "*": {"title": None, "columns": None, "glob": None, "regex": None,  # 前四个必填,parse 查
                  "file_col": False, "misses": None, "hotspot": None, "may_be_empty": False}},
    "rules": {"file_tokens": 400},
    "memory": {"index_tokens": 2000, "page_tokens": 1500, "title_ratio": 0.8},
    "review": {"level": None, "cmd": []},  # level None = 跟 size
    "lessons_dir": "docs/lessons",
    "lessons_remind": 10,
    "suggest": {"window_days": 30, "parallel_branches": 2, "overlap_files": 2, "inbox_stale_days": 30,
                "systems_medium": 4, "systems_large": 8, "down_window_days": 90},  # 或 false
}
ITEM_KEYS = {
    "check.rules": ("id", "level", "what", "why", "glob", "forbid", "require", "cmd", "timeout"),
    "scopes": ("paths", "why", "checks", "smells", "level", "review", "off"),
    "allow": ("rule", "file", "from", "to", "reason"),
}
MAP_BUDGETS = ("index_tokens", "page_tokens")
INT_SMELLS = ("file_lines", "func_lines", "clone_tokens", "clone_lines", "doc_clone_tokens", "fan_in")
# 测试路径缺省不查 D / P / S:一条内置 scope,永远排在所有用户 scope 之前(原 smells.exclude)
TEST_GLOBS = ["**/test/**", "**/tests/**", "**/__tests__/**", "test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*"]
TEST_REMOVE = ("D1", "P1", "P2", "P5", "S1", "S2")


def _bad(path, key, v):
    raise ValueError(t("CFG_BAD", path, key, v))


def _num(v, positive_int):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return False
    return isinstance(v, int) and v > 0 if positive_int else v >= 0


def _smells(sm, path, where):
    if not isinstance(sm, dict):
        _bad(path, where, sm)
    for k, v in sm.items():
        if k in INT_SMELLS and not _num(v, True) or k == "grow_slack" and not _num(v, False):
            _bad(path, "%s.%s" % (where, k), v)
        if k == "extra_ext" and not (isinstance(v, list) and all(isinstance(x, str) and re.fullmatch(r"\.[^./\\]+", x) for x in v)):
            _bad(path, "%s.%s" % (where, k), v)


def _validate(cfg, path):
    """P21 新加的键的形状;不对就退出 2(规则号唯一和 allow 指向的号要知道检测器,在 check.py 查)。"""
    if cfg.get("size", "small") not in SIZES:
        _bad(path, "size", cfg["size"])
    chk = cfg.get("check", {})
    if not isinstance(chk, dict) or not isinstance(chk.get("rules", []), list) or not all(isinstance(r, dict) for r in chk.get("rules", [])):
        _bad(path, "check", chk)
    b = chk.get("builtin")
    if b is not None and not (isinstance(b, list) and all(isinstance(x, str) and x in BUILTIN for x in b)):
        _bad(path, "check.builtin", b)
    for r in chk.get("rules", []):
        if isinstance(r.get("glob"), str):
            r["glob"] = r["glob"].strip()
    _smells(cfg.get("smells", {}), path, "smells")
    file_ids = {i for i, c in BUILTIN.items() if c == "file"} | {r.get("id") for r in chk.get("rules", []) if "cmd" not in r}
    _maps(cfg.get("map", {}), path)
    scopes = cfg.get("scopes", [])
    if not isinstance(scopes, list):
        _bad(path, "scopes", scopes)
    for n, s in enumerate(scopes):
        w = "scopes[%d]" % n
        if not isinstance(s, dict) or not isinstance(s.get("why"), str) or not s["why"].strip():
            _bad(path, w + ".why", s.get("why") if isinstance(s, dict) else s)
        ps = s.get("paths")
        if not isinstance(ps, list) or not ps or not all(isinstance(g, str) and g.strip() for g in ps):
            _bad(path, w + ".paths", ps)
        s["paths"] = ps = [g.strip() for g in ps]  # 规范化一次:匹配、具体度、B2 都用这份
        for g in ps:
            pathglob.check(g)
        ch = s.get("checks", {})
        if not isinstance(ch, dict) or set(ch) - {"add", "remove"} or \
                not all(isinstance(ch[x], list) and all(isinstance(i, str) and i in file_ids for i in ch[x]) for x in ch) or \
                set(ch.get("add", [])) & set(ch.get("remove", [])):
            _bad(path, w + ".checks", ch)
        lv = s.get("level", {})
        if not isinstance(lv, dict) or not all(i in file_ids and c in ("red", "yellow") for i, c in lv.items()):
            _bad(path, w + ".level", lv)
        if "review" in s and s["review"] not in REVIEW_LEVELS:
            _bad(path, w + ".review", s["review"])
        if "off" in s and not isinstance(s["off"], bool):
            _bad(path, w + ".off", s["off"])
        if "smells" in s:
            _smells(s["smells"], path, w + ".smells")
    allow = cfg.get("allow", [])
    if not isinstance(allow, list):
        _bad(path, "allow", allow)
    seen = set()
    for n, a in enumerate(allow):
        w = "allow[%d]" % n
        ok = isinstance(a, dict) and isinstance(a.get("rule"), str) and isinstance(a.get("reason"), str) and a["reason"].strip()
        if not ok or ("file" in a) == ("from" in a or "to" in a) or ("from" in a) != ("to" in a):
            _bad(path, w, a)
        if "file" in a:
            if not isinstance(a["file"], str):
                _bad(path, w, a)
            a["file"] = a["file"].strip()
            pathglob.check(a["file"])
        sig = json.dumps(a, sort_keys=True, ensure_ascii=False)
        if sig in seen:
            _bad(path, w, a)
        seen.add(sig)
    arch = cfg.get("arch", {})
    if not isinstance(arch, dict) or not all(isinstance(arch.get(k, []), list) for k in ("layers", "independent", "forbid", "relations")):
        _bad(path, "arch", arch)


def _maps(m, path):
    """map 段:预算是正整数;其余每个键是一张抽取表,必填 title / columns / glob / regex,可选键的类型也查。"""
    if not isinstance(m, dict):
        _bad(path, "map", m)
    for name, spec in m.items():
        w = "map." + name
        if name in MAP_BUDGETS:
            if not _num(spec, True):
                _bad(path, w, spec)
            continue
        ok = isinstance(spec, dict) and isinstance(spec.get("title"), str) and isinstance(spec.get("glob"), str) \
            and isinstance(spec.get("regex"), str) and isinstance(spec.get("columns"), list) and spec["columns"] \
            and all(isinstance(c, str) for c in spec["columns"]) and isinstance(spec.get("file_col", False), bool) \
            and isinstance(spec.get("may_be_empty", False), bool) and isinstance(spec.get("misses", ""), (str, type(None))) \
            and isinstance(spec.get("hotspot", {}), (dict, type(None)))
        if not ok:
            _bad(path, w, spec)
        pathglob.check(spec["glob"])


def _merge(d, c):
    """缺省 d 和用户 c 深合并:字典逐键,其余以用户为准。"*" 不往用户条目里补(只用于认键)。"""
    if isinstance(d, dict) and isinstance(c, dict):
        out = {k: _merge(v, {}) if isinstance(v, dict) else copy.deepcopy(v) for k, v in d.items() if k != "*"}  # 没写的段也去掉 "*"
        for k, v in c.items():
            out[k] = _merge(d[k], v) if k in d and k != "*" else copy.deepcopy(v)
        return out
    return copy.deepcopy(c)


def expanded(cfg):
    """整份展开缺省值后的配置(纯函数):check.builtin、review.level 没写时跟 size;suggest: false 保留。B2 和 Effective 用它。"""
    e = _merge(DEFAULTS, cfg)
    for name, spec in e["map"].items():  # 抽取表补可选键的缺省(map 段只有这一层的条目样子会展开)
        if name not in MAP_BUDGETS:
            e["map"][name] = dict({k: v for k, v in DEFAULTS["map"]["*"].items() if v is not None or k in ("misses", "hotspot")}, **spec)
    if e["check"]["builtin"] is None:
        e["check"]["builtin"] = list(SIZE[e["size"]]["builtin"])
    e["check"]["builtin"] = sorted(set(e["check"]["builtin"]))
    if e["review"]["level"] is None:
        e["review"]["level"] = SIZE[e["size"]]["review"]
    return e


def _specificity(g):
    """glob 的具体程度:(第一个通配符前的字面前缀长度, 字面字符总数)。"""
    m = re.search(r"[*?\[{]", g)
    return (len(g) if m is None else m.start(), len(re.sub(r"[*?\[\]{},]", "", g)))


def _scope_keys(s):
    """一条 scope 写了哪些键(合并冲突和 B2 都按这个粒度)-> {键: 值}。"""
    out = {}
    for x in ("off", "review"):
        if x in s:
            out[x] = s[x]
    for k, v in s.get("smells", {}).items():
        out["smells." + k] = v
    for i, c in s.get("level", {}).items():
        out["level." + i] = c
    for x in ("add", "remove"):
        for i in s.get("checks", {}).get(x, []):
            out["checks." + i] = x
    return out


class Effective:
    """按文件取有效配置的唯一入口:eff = Effective(cfg);eff(path) -> {off, checks, smells, level, review};eff.cfg = expanded(cfg)。
    叠加顺序:内置缺省 -> size 缺省 -> 顶层显式 -> 内置测试 scope -> 命中的用户 scopes(从最不具体到最具体逐键覆盖,不看条目先后)。
    两条一样具体、命中同一文件、写了同一个键 -> 退出 2。"""

    def __init__(self, cfg):
        self.cfg = c = expanded(cfg)
        ids = {r["id"] for r in c["check"]["rules"] if "cmd" not in r}
        self._base = {"off": False, "checks": frozenset({i for i in c["check"]["builtin"] if BUILTIN[i] == "file"} | ids),
                      "smells": dict(c["smells"]), "level": {}, "review": c["review"]["level"]}
        self._test = pathglob.matcher(TEST_GLOBS)
        self._scopes = [(s, [(pathglob.compile(g), _specificity(g)) for g in s["paths"]]) for s in c["scopes"]]
        self._memo = {}

    def __call__(self, path):
        if path in self._memo:
            return self._memo[path]
        hits = []
        for s, globs in self._scopes:
            sp = [spec for rx, spec in globs if rx.match(path)]
            if sp:
                hits.append((max(sp), s))
        hits.sort(key=lambda h: h[0])
        for i, (a, sa) in enumerate(hits):
            for b, sb in hits[i + 1:]:
                if b != a:
                    break
                both = set(_scope_keys(sa)) & set(_scope_keys(sb))
                if both:
                    raise ValueError(t("SCOPE_TIE", sa["why"], sb["why"], path, sorted(both)[0]))
        e = dict(self._base, checks=set(self._base["checks"]), smells=dict(self._base["smells"]), level={})
        if self._test(path):
            e["checks"] -= set(TEST_REMOVE)
        for _, s in hits:
            e["checks"] |= set(s.get("checks", {}).get("add", []))
            e["checks"] -= set(s.get("checks", {}).get("remove", []))
            e["smells"].update(s.get("smells", {}))
            e["level"].update(s.get("level", {}))
            for x in ("review", "off"):
                if x in s:
                    e[x] = s[x]
        e["checks"] = frozenset() if e["off"] else frozenset(e["checks"])
        self._memo[path] = e
        return e


def unknown(obj, legal, where):
    """obj 里不在 legal 里的键 -> 黄 CFG1(带最近的合法键建议)。各列表条目的校验共用。"""
    out = []
    for k in obj:
        if k not in legal:
            near = difflib.get_close_matches(k, list(legal), 1)
            key = ".".join(where + [k])
            out.append(F("yellow", "CFG1", CONFIG_NAME, 0, key, t("CFG1", key, t("CFG1_HINT", near[0]) if near else "")))
    return out


def unknown_keys(cfg):
    """nomess.json 里不认识的键(照 DEFAULTS 逐层、ITEM_KEYS 比列表条目)-> 黄 CFG1。不悄悄忽略:拼错段名会让整段检查不跑。"""
    out = []

    def walk(d, c, where):
        if not (isinstance(d, dict) and isinstance(c, dict)):
            return
        out.extend(unknown(c, [k for k in d if k != "*"] if "*" not in d else list(c), where))
        for k, v in c.items():
            if k in d and k != "*":
                walk(d[k], v, where + [k])
            elif "*" in d:
                walk(d["*"], v, where + [k])
    walk(DEFAULTS, cfg, [])
    for dotted, legal in ITEM_KEYS.items():
        sec = cfg
        for part in dotted.split("."):
            sec = sec.get(part, {}) if isinstance(sec, dict) else {}
        for n, item in enumerate(sec if isinstance(sec, list) else []):
            if isinstance(item, dict):
                out += unknown(item, legal, ["%s[%d]" % (dotted, n)])
    return out


# B2:两份展开后的配置逐键比,表里没有的键不比(size 的效果已在 check.builtin、review.level 里)。
# 判法:superset 只许增;superset_ordered 只许增且已有条目相对顺序不变;by_id 按 id 删或改(level 黄改红除外)都算;
# same 任何改动;le 变大;ge 档变低;scopes / tables 见各自函数。
LOOSEN = [
    ("check.builtin", "superset"),
    ("check.rules", "by_id"),
    ("check.baseline", "same"),
    ("smells.file_lines", "le"),
    ("smells.func_lines", "le"),
    ("smells.clone_tokens", "le"),
    ("smells.clone_lines", "le"),
    ("smells.doc_clone_tokens", "le"),
    ("smells.grow_slack", "le"),
    ("smells.extra_ext", "superset"),
    ("review.level", "ge"),
    ("scopes", "scopes"),
    ("arch.layers", "superset_ordered"),
    ("arch.independent", "superset"),
    ("arch.forbid", "superset"),
    ("arch.relations", "by_id"),
    ("systems", "same"),
    ("map", "tables"),
    # >>> P22 只在这两行之间追加
    # <<< P22
    # >>> P23 只在这两行之间追加
    # <<< P23
    # >>> P24 只在这两行之间追加
    # <<< P24
    # >>> P25 只在这两行之间追加
    # <<< P25
]


def _get(d, dotted):
    for part in dotted.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def _sig(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def _by_id(old, new):
    nd = {r.get("id"): r for r in new}
    out = []
    for r in old:
        n = nd.get(r.get("id"))
        if n is None:
            out.append("-" + str(r.get("id")))
        elif n != r and not (dict(n, level=r.get("level")) == r and r.get("level") == "yellow" and n.get("level") == "red"):
            out.append(str(r.get("id")))
    return out


# 只写一边也不会变松的键值:新加最严的、删掉最松的
_STRICTEST = lambda k, v: (k.startswith("checks.") and v == "add") or (k.startswith("level.") and v == "red") or (k == "review" and v == "strict") or (k == "off" and v is False)  # noqa: E731
_LOOSEST = lambda k, v: (k.startswith("checks.") and v == "remove") or (k.startswith("level.") and v == "yellow") or (k == "review" and v == "off") or (k == "off" and v is True)  # noqa: E731


def _scopes(old, new):
    def by_glob(scopes):
        m = {}
        for s in scopes:
            for g in s["paths"]:
                m.setdefault(g, {}).update(_scope_keys(s))
        return m
    a, b = by_glob(old), by_glob(new)
    out = ["+" + g for g in sorted(set(b) - set(a))] + ["-" + g for g in sorted(set(a) - set(b))]
    rank = REVIEW_LEVELS.index
    for g in sorted(set(a) & set(b)):
        for k in sorted(set(a[g]) | set(b[g])):
            if k in a[g] and k in b[g]:
                x, y = a[g][k], b[g][k]
                loose = (k == "smells.extra_ext" and not set(y) >= set(x)) or \
                        (k.startswith("smells.") and k != "smells.extra_ext" and y > x) or \
                        (k.startswith("checks.") and (x, y) == ("add", "remove")) or (k.startswith("level.") and (x, y) == ("red", "yellow")) or \
                        (k == "review" and rank(y) < rank(x)) or (k == "off" and (x, y) == (False, True))
            elif k in b[g]:
                loose = not _STRICTEST(k, b[g][k])
            else:
                loose = not _LOOSEST(k, a[g][k])
            if loose:
                out.append("%s %s" % (g, k))
    return out


def _tables(old, new):
    out = []
    for name, spec in old.items():
        if not isinstance(spec, dict):
            continue  # index_tokens / page_tokens:预算,不影响检查结果
        n = new.get(name)
        if not isinstance(n, dict):
            out.append("-" + name)
            continue
        out += ["%s.%s" % (name, k) for k in ("glob", "regex", "columns") if n.get(k) != spec.get(k)]
        if n.get("may_be_empty") and not spec.get("may_be_empty"):
            out.append(name + ".may_be_empty")
    return out


def loosened(old, new):
    """两份 expanded() 后的配置 -> [(键路径, 说明)],每项一条 B2。"""
    out = []
    for path, how in LOOSEN:
        x, y = _get(old, path), _get(new, path)
        if how == "superset":
            ys = {_sig(v) for v in y or []}
            diff = [_sig(v) for v in x or [] if _sig(v) not in ys]
        elif how == "superset_ordered":
            xs = [_sig(v) for v in x or []]
            kept = [s for s in (_sig(v) for v in y or []) if s in xs]
            diff = [s for s in xs if s not in kept] or (["order"] if kept != xs else [])
        elif how == "by_id":
            diff = _by_id(x or [], y or [])
        elif how == "same":
            diff = ["%s -> %s" % (_sig(x), _sig(y))] if x != y else []
        elif how == "le":
            diff = ["%s -> %s" % (x, y)] if y > x else []
        elif how == "ge":
            diff = ["%s -> %s" % (x, y)] if REVIEW_LEVELS.index(y) < REVIEW_LEVELS.index(x) else []
        elif how == "scopes":
            diff = _scopes(x or [], y or [])
        else:
            diff = _tables(x or {}, y or {})
        out += [(path, d) for d in diff]
    return out


def est_tokens(s):
    """估算 token:中文按字数,其余按字符数 / 4。预算类检查(记忆、规则文件、AGENTS.md、系统图首页)共用。"""
    cjk = len(re.findall(r"[㐀-鿿　-〿＀-￯]", s))
    return cjk + (len(s) - cjk + 3) // 4


def glob_files(d, pattern, recursive=False):
    """目录 d 下匹配 pattern 的路径(排序);d 当字面路径用(glob.escape),只有 pattern 展开。"""
    return sorted(glob.glob(os.path.join(glob.escape(d), pattern), recursive=recursive))


def no_link(base, rel):
    """base/rel 的真实位置必须就是 base 的真实位置下的 rel:路径上任何一段(目录或文件本身)是符号链接 / junction 就 ValueError,
    防止生成物的写入和清理被链接导到别处。在写任何文件之前对输出目录和每个要写、要删的文件调用。"""
    p = os.path.join(base, rel)
    if os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.join(os.path.realpath(base), os.path.normpath(rel))):
        raise ValueError(t("OUT_LINK", p))


def atomic_write(path, data):
    """写 path:data 是 bytes 原样写,是 str 按 UTF-8 写(换行不转换)。先写同目录临时文件再 os.replace;
    已有文件保留原权限(否则可执行脚本会从 100755 变 100644)。"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".nomess-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode("utf-8") if isinstance(data, str) else data)
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
