"""D1 复制粘贴、PL-DUP 文档重复段落。做法照 CPD / jscpd 的 token 序列加 winnowing 指纹(Schleimer 等 2003),命中后向两边扩到最长:
  - 每个文件缓存去注释去空白后的 token 数和指纹(只和这个文件的内容有关,缓存说明见 scripts/README.md "P23");
  - 全树指纹索引、两个文件撞上、扩到多长、是否一字不差,每次在内存里现算;
  - 一字不差(精确指纹 + 精确 token 扩展)红;只在标识符归一后才相同的(改了名字的结构克隆)黄;PL-DUP 只有黄。
只查同一对不同文件之间的重复,不查同一个文件内部。阈值取两边 eff(path)["smells"] 里更小的(更严的)。"""
import base64
import os
import re
import sys
import zlib
from array import array
from bisect import bisect_left, bisect_right
from collections import deque
from itertools import accumulate, repeat

import cache
import deps
import docgen
import lessons
import nm_config
import pathglob
import snapshot
from messages import add, t

ANALYZER = 4  # 改分词或指纹逻辑就加一,旧缓存整批作废
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
# 组:1 注释、2 字符串、3 数字、4 标识符;不进组的 \S 是单字符符号。空白不匹配任何分支,finditer 在 C 里直接跳过
_TOKEN = {fam: re.compile(r"(%s)|(%s)|(%s)|(%s)|\S" % (com, st, _NUM, _ID)) for fam, com, st in (
    ("c", r"//[^\n]*|/\*[\s\S]*?\*/", _STR_C),
    ("hash", r"\#[^\n]*", _STR_H),
    ("other", r"(?!)", _STR_C),
)}
_NORM = {2: "$S", 3: "$N"}


def is_source(eff, path):
    """path 算源码:扩展名在 deps.EXT_LANG 里,或在这个文件自己的有效配置 smells.extra_ext 里(目录级 scope 可以加)。"""
    ext = os.path.splitext(path)[1]
    return ext in deps.EXT_LANG or ext in eff(path)["smells"]["extra_ext"]


def sources(snap, eff):
    """快照里的源码文件(is_source)。"""
    return [p for p in deps.all_files(snap) if is_source(eff, p)]


def family(path):
    ext = os.path.splitext(path)[1]
    lang = deps.EXT_LANG.get(ext)
    if ext in HASH_EXT or lang == "py":
        return "hash"
    return "c" if lang else "other"


def tokenize(text, fam):
    """(精确 token, 归一 token, 行号) 三个等长列表:去注释和空白;归一 = 标识符(非关键字)换 $I、字符串 $S、数字 $N。"""
    toks = [m for m in _TOKEN[fam].finditer(text) if m.lastindex != 1]
    ex = [m.group() for m in toks]
    no = [_NORM.get(k) or ("$I" if k == 4 and s not in KEYWORDS else s) for s, k in zip(ex, [m.lastindex for m in toks])]
    starts = [m.start() for m in toks]
    # 行号 = 1 + 开头到 token 起点的换行数,逐段累加(批量在 C 里数)
    ln = list(accumulate(map(text.count, repeat("\n"), [0] + starts[:-1], starts), initial=1))[1:]
    return ex, no, ln


def text_of(snap, path):
    return snap.text(path).replace("\r\n", "\n")


# ---------------------------------------------------------------- winnowing

def winnow(seq):
    """seq 的 K-gram 指纹,平铺成 [哈希, 起始 token 序号, 哈希, 序号, ...](哈希取低 32 位,命中后逐 token 核对,碰撞无妨;不存行号,进缓存前用 _pack 编成一个串,都是为了缓存小、读得快):每个 W 组的窗口取最小哈希(并列取最右),连续相同位置只记一次。"""
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


def _pack(fp):
    """平铺指纹存进缓存的样子:32 位无符号小端数组的 base64 串(JSON 解析、缓存返回副本都只碰一个字符串,用到时才 _unpack)。"""
    a = array("I", fp)
    if sys.byteorder == "big":
        a.byteswap()
    return base64.b64encode(a.tobytes()).decode("ascii")


def _unpack(s):
    a = array("I", base64.b64decode(s))
    if sys.byteorder == "big":
        a.byteswap()
    return a


def _code_facts(text, fam):
    ex, no, _ = tokenize(text, fam)
    return {"n": len(ex), "x": _pack(winnow(ex)), "m": _pack(winnow(no))}


_WORD = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


def doc_tokens(text):
    """文档 token:英文数字词和单个汉字;不要生成段(docgen.gen_ranges,含标记行)和围栏代码块(lessons.in_fence),行号照原文。"""
    lines = text.split("\n")
    skip = lessons.in_fence(lines)
    for a, b in docgen.gen_ranges(text):
        skip[a - 1:b] = [True] * (b - a + 1)
    ex, ln = [], []
    for n, line in enumerate(lines, 1):
        if skip[n - 1]:
            continue
        for w in _WORD.findall(line):
            ex.append(w.lower())
            ln.append(n)
    return ex, ln


def _doc_facts(text):
    ex, _ = doc_tokens(text)
    return {"n": len(ex), "x": _pack(winnow(ex))}


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


def _index(fps, queries):
    """查询文件的指纹哈希在全树里的位置:{哈希: [(文件, token 序号)]}(只为查询要用的哈希建,不为全树建)。fps = {文件: 平铺指纹}。
    出现在超过 COMMON 个文件里的哈希是样板(每个文件都有的 import 头、成排相同结构的语句):不拿它当种子,否则 N 个文件两两配对、
    耗时随 N 平方涨;照 MOSS 对公共 k-gram 的做法(Schleimer 等 2003)。"""
    wanted = {h for q in queries if q in fps for h in fps[q][::2]}
    idx = {}
    for p, f in fps.items():
        hs = f[::2]
        if wanted.isdisjoint(hs):  # 大多数文件和查询文件不沾边:整批在 C 里判掉
            continue
        for h, i in zip(hs, f[1::2]):
            if h in wanted:
                idx.setdefault(h, []).append((p, i))
    common = {h for h, v in idx.items() if len({p for p, _i in v}) > COMMON}
    return {h: v for h, v in idx.items() if h not in common}, common


def _seeds(q, fps, index, common, ok_pair, posmaps):
    """q 的种子:{(o, 对角线 d = o 序号 - q 序号): ((最少 token, 最少行), [q 的 token 序号, 升序])}。fps = {文件: 平铺指纹};
    ok_pair(o) -> 阈值或 None(这一对不查);posmaps 是调用方给的空字典,存各文件 {token 序号: 哈希}(按需建)。
    剪枝(不读文件就能判,结果不变):长度 >= thr 的重复里任取含种子 i 的一段长 thr 的子段,其中 M = thr-K+1 个 K-gram、
    起点相隔 W 的窗口两两不交、整个落在子段里的有 M // W 个,各自选中的位置在两个文件里都是指纹(同一对角线、同一哈希),
    位置都在 [i-(thr-K), i+(thr-K)] 内。这些共同指纹要么是同一对角线上的种子,要么是样板哈希(common,不进索引,到 o 的指纹里核对);
    范围内不够 M // W 个的种子扩不到 thr,不用扩。"""
    qfp = fps[q]
    seeds = {}
    for h, i in _pairs(qfp):
        for o, j in index.get(h, ()):
            if o != q:
                seeds.setdefault((o, j - i), []).append(i)
    cfp = [(i, h) for h, i in _pairs(qfp) if h in common]
    cpos = [i for i, _h in cfp]
    out = {}
    for (o, d), starts in sorted(seeds.items()):
        thr = ok_pair(o)
        if thr is None:
            continue
        span, need = thr[0] - K, (thr[0] - K + 1) // W
        if need > 1:
            if o not in posmaps:
                posmaps[o] = dict(zip(fps[o][1::2], fps[o][::2]))
            om = posmaps[o]
            lo, hi = bisect_left(cpos, starts[0] - span), bisect_right(cpos, starts[-1] + span)
            shared = sorted(starts + [i for i, h in cfp[lo:hi] if om.get(i + d) == h])
            starts = [i for i in starts if bisect_right(shared, i + span) - bisect_left(shared, i - span) >= need]
        if starts:
            out[(o, d)] = (thr, starts)
    return out


def _find(qseq, qln, seeds, load, skip=None):
    """克隆区间 [(o, q 起, q 止, o 起)]。seeds 来自 _seeds;load(o) -> (o 的 seq, o 的行号);
    skip(o, q 起, q 止) 为真的区间不要(归一克隆让给同一处已有的精确克隆)。"""
    out, covered = [], {}
    for (o, d), (thr, starts) in seeds.items():
        oseq, _ = load(o)
        for i in starts:
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
    srcs = sources(snap, eff)
    queries = [p for p in changed if is_source(eff, p)]
    if not queries or not any("D1" in eff(p)["checks"] for p in srcs):
        return []
    facts = {p: cache.facts(snap, p, "clones.tok." + family(p), ANALYZER, lambda s, f=family(p): _code_facts(s, f)) for p in srcs}
    fp = {v: {p: _unpack(f[v]) for p, f in facts.items() if f is not None} for v in ("x", "m")}
    idx = {v: _index(fp[v], queries) for v in ("x", "m")}
    posmaps = {"x": {}, "m": {}}
    toks = {}

    def tok(p):
        if p not in toks:
            toks[p] = tokenize(text_of(snap, p), family(p))
        return toks[p]

    found, seen = [], set()
    for q in queries:
        if q not in fp["x"]:
            continue
        qon = "D1" in eff(q)["checks"]

        def ok_pair(o, q=q, qon=qon):
            if not qon and "D1" not in eff(o)["checks"]:
                return None  # 两边都关了 D1;只要有一边开着就照查(阈值取小)
            return (min(_min_tokens(eff, q, "clone_tokens"), _min_tokens(eff, o, "clone_tokens")),
                    min(eff(q)["smells"]["clone_lines"], eff(o)["smells"]["clone_lines"]))

        sx, sm = (_seeds(q, fp[v], *idx[v], ok_pair, posmaps[v]) for v in ("x", "m"))
        if not (sx or sm):
            continue  # 没有能扩到阈值的种子:不用为它分词
        qx, qm, qln = tok(q)
        exact = _find(qx, qln, sx, lambda o: (tok(o)[0], tok(o)[2]))
        by_o = {}
        for o, qs, qe, _os in exact:
            by_o.setdefault(o, []).append((qs, qe))
        ren = _find(qm, qln, sm, lambda o: (tok(o)[1], tok(o)[2]),
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
    fp = {p: _unpack(f["x"]) for p, f in facts.items() if f is not None}
    idx = _index(fp, queries)
    thr = eff.cfg["smells"]["doc_clone_tokens"]
    toks = {}

    def tok(p):
        if p not in toks:
            toks[p] = doc_tokens(text_of(snap, p))
        return toks[p]

    found, seen = [], set()
    for q in queries:
        if q not in fp:
            continue
        seeds = _seeds(q, fp, *idx, lambda o: (thr, 0), {})
        if not seeds:
            continue
        qx, qln = tok(q)
        for o, qs, qe, os_ in _find(qx, qln, seeds, tok):
            k = _kid(qx, qs)
            if (frozenset((q, o)), k) in seen:
                continue
            seen.add((frozenset((q, o)), k))
            oln = tok(o)[1]
            a, b, c, d = qln[qs], qln[qe - 1], oln[os_], oln[os_ + qe - qs - 1]
            found.append(nm_config.F("yellow", "PL-DUP", q, a, "%s:%d-%d ~ %s:%d-%d" % (q, a, b, o, c, d),
                                     t("CL_DOC", q, a, b, o, c, d, qe - qs), k=[k], also=[o]))
    return found
