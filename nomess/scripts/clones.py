"""D1 复制粘贴、PL-DUP 文档重复段落。做法照 CPD / jscpd 的 token 序列加 winnowing 指纹(Schleimer 等 2003),命中后向两边扩到最长:
  - 每个文件缓存去注释去空白后的 token 数和指纹(只和这个文件的内容有关,缓存说明见 scripts/README.md "P23");
  - 全树指纹索引、两个文件撞上、扩到多长、是否一字不差,每次在内存里现算;
  - 一字不差(精确指纹 + 精确 token 扩展)红;只在标识符归一后才相同的(改了名字的结构克隆)黄;PL-DUP 只有黄。
只查同一对不同文件之间的重复,不查同一个文件内部。阈值取两边 eff(path)["smells"] 里更小的(更严的)。"""
import os
import re
import zlib
from collections import deque

import cache
import deps
import docgen
import nm_config
import pathglob
import snapshot
from messages import add, t

ANALYZER = 2  # 改分词或指纹逻辑就加一,旧缓存整批作废
K, W = 25, 26  # 指纹:K 个 token 一组、W 组一个窗口;长度 >= K+W-1 的重复必有共同指纹
MIN_TOKENS = K + W - 1
COMMON = 10  # 一个指纹出现在超过这么多个文件里就当样板
_BASE, _MOD, _MASK = 1000003, (1 << 61) - 1, 0xFFFFFFFF
_TOP = pow(_BASE, K - 1, _MOD)

M = {
    "CL_D1_WHAT": ("copy-pasted code (same token run in two files)", "复制粘贴的代码(两个文件里有同一段 token)"),
    "CL_D1_WHY": ("Two copies drift apart; extract it, or keep one", "两份拷贝会各改各的;抽成一处,或只留一份"),
    "CL_PLDUP_WHAT": ("repeated paragraph across docs", "文档之间重复的段落"),
    "CL_PLDUP_WHY": ("The same fact written twice goes stale in one place; keep one home and link", "同一件事写两处会有一处过时;只留一个家,别处链接"),
    "CL_EXACT": ("%s lines %d-%d repeats %s lines %d-%d (%d tokens, identical)", "%s 第 %d-%d 行和 %s 第 %d-%d 行重复(%d 个 token,一字不差)"),
    "CL_RENAMED": ("%s lines %d-%d repeats %s lines %d-%d with renamed identifiers (%d tokens)", "%s 第 %d-%d 行和 %s 第 %d-%d 行结构相同、只改了名字(%d 个 token)"),
    "CL_DOC": ("%s lines %d-%d repeats %s lines %d-%d (%d tokens)", "%s 第 %d-%d 行和 %s 第 %d-%d 行重复(%d 个 token)"),
    "CL_MIN": ("smells.%s = %d is below the minimum %d the fingerprints guarantee; raise it in %s",
               "smells.%s = %d 低于指纹能保证的下限 %d;在 %s 里调高"),
}
add(M)
RULES = [
    {"id": "D1", "level": "red", "what": "CL_D1_WHAT", "why": "CL_D1_WHY"},
    {"id": "PL-DUP", "level": "yellow", "what": "CL_PLDUP_WHAT", "why": "CL_PLDUP_WHY"},
]

# ---------------------------------------------------------------- 源码范围和分词(smells 共用)

HASH_EXT = {".py", ".rb", ".sh", ".pl", ".r", ".yml", ".yaml", ".toml"}  # 用 # 写注释的扩展名;deps.EXT_LANG 里的其余语言按 C 系
KEYWORDS = frozenset("""if else elif for while do return def class function import from export as in is not and or try except catch
finally raise throw new const let var self this true false none null lambda with yield async await switch case break continue pass
static public private protected void int float bool string char const let fn func struct enum interface type package use mod impl
trait where match loop mut ref pub extends implements super default global nonlocal del assert elif end then begin""".split())
_NUM = r"\d[\w.]*"
_ID = r"[^\W\d]\w*"
_STR_C = r"""`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'"""
_STR_H = r'''\"\"\"[\s\S]*?\"\"\"|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*\''''
_TOKEN = {
    "c": re.compile(r"(?P<sp>\s+|//[^\n]*|/\*[\s\S]*?\*/)|(?P<s>%s)|(?P<n>%s)|(?P<i>%s)|(?P<o>\S)" % (_STR_C, _NUM, _ID)),
    "hash": re.compile(r"(?P<sp>\s+|\#[^\n]*)|(?P<s>%s)|(?P<n>%s)|(?P<i>%s)|(?P<o>\S)" % (_STR_H, _NUM, _ID)),
    "other": re.compile(r"(?P<sp>\s+)|(?P<s>%s)|(?P<n>%s)|(?P<i>%s)|(?P<o>\S)" % (_STR_C, _NUM, _ID)),
}


def source_exts(eff):
    return set(deps.EXT_LANG) | set(eff.cfg["smells"]["extra_ext"])


def sources(snap, eff):
    """快照里的源码文件(扩展名在 deps.EXT_LANG 或 smells.extra_ext 里)。"""
    exts = source_exts(eff)
    return [p for p in deps.all_files(snap) if os.path.splitext(p)[1] in exts]


def family(path):
    ext = os.path.splitext(path)[1]
    lang = deps.EXT_LANG.get(ext)
    if ext in HASH_EXT or lang == "py":
        return "hash"
    return "c" if lang else "other"


def tokenize(text, fam):
    """(精确 token, 归一 token, 行号) 三个等长列表:去注释和空白;归一 = 标识符(非关键字)换 $I、字符串 $S、数字 $N。"""
    ex, no, ln = [], [], []
    line, pos = 1, 0
    for m in _TOKEN[fam].finditer(text):
        a, b = m.start(), m.end()
        line += text.count("\n", pos, a)
        pos = a
        kind = m.lastgroup
        if kind != "sp":
            s = m.group()
            ex.append(s)
            no.append("$S" if kind == "s" else "$N" if kind == "n" else "$I" if kind == "i" and s not in KEYWORDS else s)
            ln.append(line)
        line += text.count("\n", a, b)
        pos = b
    return ex, no, ln


def text_of(snap, path):
    return snap.text(path).replace("\r\n", "\n")


# ---------------------------------------------------------------- winnowing

def winnow(seq):
    """seq 的 K-gram 指纹,平铺成 [哈希, 起始 token 序号, 哈希, 序号, ...](哈希取低 32 位,命中后逐 token 核对,碰撞无妨;平铺和不存行号是为了缓存小、读得快):每个 W 组的窗口取最小哈希(并列取最右),连续相同位置只记一次。"""
    ids = [zlib.crc32(x.encode("utf-8")) for x in seq]
    if len(ids) < K:
        return []
    g, h = [], 0
    for j, x in enumerate(ids):
        if j >= K:
            h = (h - ids[j - K] * _TOP) % _MOD
        h = (h * _BASE + x) % _MOD
        if j >= K - 1:
            g.append(h)
    out, dq, last = [], deque(), -1
    for i, v in enumerate(g):
        while dq and dq[-1][0] >= v:
            dq.pop()
        dq.append((v, i))
        if dq[0][1] <= i - W:
            dq.popleft()
        if i >= W - 1 or i == len(g) - 1:
            v0, i0 = dq[0]
            if i0 != last:
                out += (v0 & _MASK, i0)
                last = i0
    return out


def _code_facts(text, fam):
    ex, no, _ = tokenize(text, fam)
    return {"n": len(ex), "x": winnow(ex), "m": winnow(no)}


_GEN = re.compile(r"<!-- GEN:(\S+) BEGIN -->")
_WORD = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


def doc_tokens(text):
    """文档 token:英文数字词和单个汉字;不要生成段(docgen 标记之间)和围栏代码块,行号照原文。"""
    ex, ln = [], []
    gen_end, fence = None, False
    for n, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if gen_end is not None:
            if s == gen_end:
                gen_end = None
            continue
        m = _GEN.fullmatch(s)
        if m:
            gen_end = docgen.markers(m.group(1))[1]
            continue
        if s.startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        for w in _WORD.findall(line):
            ex.append(w.lower())
            ln.append(n)
    return ex, ln


def _doc_facts(text):
    ex, _ = doc_tokens(text)
    return {"n": len(ex), "x": winnow(ex)}


# ---------------------------------------------------------------- 查找

def _check_min(key, v):
    if v < MIN_TOKENS:
        raise ValueError(t("CL_MIN", key, v, MIN_TOKENS, nm_config.CONFIG_NAME))
    return v


def _min_tokens(eff, path, key):
    return _check_min(key, eff(path)["smells"][key])


def _extend(a, b, i, j):
    """a[i:i+K] 和 b[j:j+K] 一致(哈希碰撞就返回 None);向两边扩到最长 -> (a 起, a 止, b 起)。"""
    if a[i:i + K] != b[j:j + K]:
        return None
    s = 0
    while i - s - 1 >= 0 and j - s - 1 >= 0 and a[i - s - 1] == b[j - s - 1]:
        s += 1
    e = K
    while i + e < len(a) and j + e < len(b) and a[i + e] == b[j + e]:
        e += 1
    return i - s, i + e, j - s


def _pairs(fp):
    return zip(fp[::2], fp[1::2])


def _index(facts, variant, wanted):
    """查询文件的指纹哈希 wanted 在全树里的位置:{哈希: [(文件, token 序号)]}(只为查询要用的哈希建,不为全树建)。
    出现在超过 COMMON 个文件里的哈希是样板(每个文件都有的 import 头、成排相同结构的语句):不拿它当种子,否则 N 个文件两两配对、
    耗时随 N 平方涨;照 MOSS 对公共 k-gram 的做法(Schleimer 等 2003)。"""
    idx = {}
    for p, f in facts.items():
        for h, i in _pairs(f[variant]):
            if h in wanted:
                idx.setdefault(h, []).append((p, i))
    return {h: v for h, v in idx.items() if len({p for p, _i in v}) <= COMMON}


def _has_seed(q, fps, index):
    return any(o != q for h, _i in _pairs(fps) for o, _j in index.get(h, ()))


def _find(q, qseq, qln, qfp, index, load, ok_pair, skip=None):
    """q 对索引里别的文件的克隆区间 [(o, q 起, q 止, o 起)]。load(o) -> (o 的 seq, o 的行号);ok_pair(o) -> (最少 token, 最少行) 或 None
    (这一对不查)。skip(o, q 起, q 止) 为真的区间不要(归一克隆让给同一处已有的精确克隆)。"""
    seeds = {}
    for h, i in _pairs(qfp):
        for o, j in index.get(h, ()):
            if o != q:
                seeds.setdefault((o, j - i), []).append(i)
    out, covered = [], {}
    for (o, d), starts in sorted(seeds.items()):
        thr = ok_pair(o)
        if thr is None:
            continue
        oseq, _ = load(o)
        for i in sorted(starts):
            if any(a <= i < b for a, b in covered.get((o, d), ())):
                continue
            r = _extend(qseq, oseq, i, i + d)
            if r is None:
                continue
            qs, qe, os_ = r
            covered.setdefault((o, d), []).append((qs, qe))
            if qe - qs >= thr[0] and qln[qe - 1] - qln[qs] + 1 >= thr[1] and not (skip and skip(o, qs, qe)):
                out.append((o, qs, qe, os_))
    # 重复结构(每行都一样的表)会在错开的对角线上也命中:q 区间整个落在同一个 o 的更长区间里的丢掉
    out.sort(key=lambda r: r[1] - r[2])
    kept = []
    for r in out:
        if not any(k[0] == r[0] and k[1] <= r[1] and r[2] <= k[2] for k in kept):
            kept.append(r)
    return kept


def _kid(seq, i):
    return "%08x" % zlib.crc32("\0".join(seq[i:i + K]).encode("utf-8"))


def run(snap, changes, eff):
    out = []
    smells = eff.cfg["smells"]
    for key in ("clone_tokens", "doc_clone_tokens"):
        _check_min(key, smells[key])
    changed = sorted(p for p, st in changes.items() if st != "D")
    if not changed:
        return out
    out += _run_d1(snap, changed, eff)
    if "PL-DUP" in eff.cfg["check"]["builtin"]:
        out += _run_docs(snap, changed, eff)
    return out


def _run_d1(snap, changed, eff):
    exts = source_exts(eff)
    srcs = sources(snap, eff)
    queries = [p for p in changed if os.path.splitext(p)[1] in exts]
    if not queries or not any("D1" in eff(p)["checks"] for p in srcs):
        return []
    facts = {p: cache.facts(snap, p, "clones.tok." + family(p), ANALYZER, lambda s, f=family(p): _code_facts(s, f)) for p in srcs}
    facts = {p: f for p, f in facts.items() if f is not None}
    idx = {v: _index(facts, v, {h for q in queries if q in facts for h in facts[q][v][::2]}) for v in ("x", "m")}
    toks = {}

    def tok(p):
        if p not in toks:
            toks[p] = tokenize(text_of(snap, p), family(p))
        return toks[p]

    found, seen = [], set()
    for q in queries:
        if q not in facts:
            continue
        qon = "D1" in eff(q)["checks"]

        def ok_pair(o, q=q, qon=qon):
            if not qon and "D1" not in eff(o)["checks"]:
                return None  # 两边都关了 D1;只要有一边开着就照查(阈值取小)
            return (min(_min_tokens(eff, q, "clone_tokens"), _min_tokens(eff, o, "clone_tokens")),
                    min(eff(q)["smells"]["clone_lines"], eff(o)["smells"]["clone_lines"]))

        if not (_has_seed(q, facts[q]["x"], idx["x"]) or _has_seed(q, facts[q]["m"], idx["m"])):
            continue  # 没有和别的文件共用的指纹:不用为它分词
        qx, qm, qln = tok(q)
        exact = _find(q, qx, qln, facts[q]["x"], idx["x"], lambda o: (tok(o)[0], tok(o)[2]), ok_pair)
        by_o = {}
        for o, qs, qe, _os in exact:
            by_o.setdefault(o, []).append((qs, qe))
        ren = _find(q, qm, qln, facts[q]["m"], idx["m"], lambda o: (tok(o)[1], tok(o)[2]), ok_pair,
                    skip=lambda o, qs, qe: any(qs < b and a < qe for a, b in by_o.get(o, ())))
        for red, regions in ((True, exact), (False, ren)):
            for o, qs, qe, os_ in regions:
                oln = tok(o)[2]
                k = _kid(qx if red else qm, qs)
                key = (frozenset((q, o)), red, k)
                if key in seen:
                    continue
                seen.add(key)
                a, b, c, d = qln[qs], qln[qe - 1], oln[os_], oln[os_ + qe - qs - 1]
                found.append(nm_config.F("red" if red else "yellow", "D1", q, a, "%s:%d-%d ~ %s:%d-%d" % (q, a, b, o, c, d),
                                         t("CL_EXACT" if red else "CL_RENAMED", q, a, b, o, c, d, qe - qs), k=[k], also=[o]))
    return found


def _run_docs(snap, changed, eff):
    rx = pathglob.compile("docs/**/*.md")
    docs = [p for p in deps.all_files(snap) if rx.match(p)]
    queries = [p for p in changed if rx.match(p)]
    if not queries:
        return []
    facts = {p: cache.facts(snap, p, "clones.doc", ANALYZER, _doc_facts) for p in docs}
    facts = {p: f for p, f in facts.items() if f is not None}
    idx = _index(facts, "x", {h for q in queries if q in facts for h in facts[q]["x"][::2]})
    thr = eff.cfg["smells"]["doc_clone_tokens"]
    toks = {}

    def tok(p):
        if p not in toks:
            toks[p] = doc_tokens(text_of(snap, p))
        return toks[p]

    found, seen = [], set()
    for q in queries:
        if q not in facts:
            continue
        if not _has_seed(q, facts[q]["x"], idx):
            continue
        qx, qln = tok(q)
        for o, qs, qe, os_ in _find(q, qx, qln, facts[q]["x"], idx, tok, lambda o: (thr, 0)):
            k = _kid(qx, qs)
            if (frozenset((q, o)), k) in seen:
                continue
            seen.add((frozenset((q, o)), k))
            oln = tok(o)[1]
            a, b, c, d = qln[qs], qln[qe - 1], oln[os_], oln[os_ + qe - qs - 1]
            found.append(nm_config.F("yellow", "PL-DUP", q, a, "%s:%d-%d ~ %s:%d-%d" % (q, a, b, o, c, d),
                                     t("CL_DOC", q, a, b, o, c, d, qe - qs), k=[k], also=[o]))
    return found
