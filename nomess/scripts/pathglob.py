"""路径 glob 的唯一实现:规则文件的 paths、条目的 `路径:`、nomess.json 的 systems 都用它判断归属,语义对齐 Claude Code 的规则 paths。
出处:https://code.claude.com/docs/en/memory#path-specific-rules(2026-11-18 核实):
  `*.md` 不带斜杠 = 基准目录下任意层;`/*.md` 开头斜杠 = 只在基准目录;带斜杠的 `src/x/*.tsx` 从基准目录算、`*` 不跨目录;
  `**` 任意层目录;`{a,b}` 花括号展开(整份 paths 最多展开 1000 个);`[abc]` 字符组,`\\[` 转义成字面。
不支持、明确拒绝(ValueError):`!` 开头的取反、以 `/` 结尾、`[` 配不上 `]`、花括号不配对或展开超过 1000 个。
路径一律是相对基准目录、用 / 分隔的写法(git ls-files 的输出)。"""
import re

MAX_EXPAND = 1000


def _split_top(s):
    """花括号里按顶层逗号切;反斜杠转义的字符原样保留。"""
    out, depth, cur, i = [], 0, "", 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            cur += s[i:i + 2]
            i += 2
            continue
        depth += (ch == "{") - (ch == "}")
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    return out + [cur]


def split_globs(s):
    """逗号分隔的 glob 列表;花括号里的逗号不是分隔符;空项丢掉。"""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch == "{") - (ch == "}")
        if ch == "," and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [g.strip() for g in out + [cur] if g.strip()]


def expand(g):
    """花括号展开成若干个不带花括号的模式。"""
    i, depth, start = 0, 0, None
    while i < len(g):
        c = g[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth:
            depth -= 1
            if depth == 0:
                head, body, tail = g[:start], g[start + 1:i], g[i + 1:]
                if "," not in body:
                    raise ValueError("glob %r: {} without a comma is not supported" % g)
                out = [head + x + t for a in _split_top(body) for x in expand(a) for t in expand(tail)]
                if len(out) > MAX_EXPAND:
                    raise ValueError("glob %r: brace expansion over %d patterns" % (g, MAX_EXPAND))
                return out
        i += 1
    if depth:
        raise ValueError("glob %r: unbalanced {" % g)
    return [g]


def _bracket(g, i):
    """g[i] 是 `[`;返回 (正则字符组, 下一个下标)。配不上 `]` 或组里有 / 就 ValueError。"""
    j = i + 1
    neg = j < len(g) and g[j] in "!^"
    j += neg
    body, first = "", True
    while j < len(g) and (g[j] != "]" or first):
        if g[j] == "/":
            break
        if g[j] == "\\" and j + 1 < len(g):
            body += re.escape(g[j + 1])
            j += 2
        else:
            body += "-" if g[j] == "-" else re.escape(g[j])
            j += 1
        first = False
    if j >= len(g) or g[j] != "]":
        raise ValueError("glob %r: [ without a matching ]" % g)
    return ("[^/%s]" % body) if neg else ("(?!/)[%s]" % body), j + 1


def _one(g):
    if g.startswith("!") or g.endswith("/") or not g:
        raise ValueError("glob %r: negation, trailing / and empty patterns are not supported" % g)
    if g.startswith("/"):
        g, prefix = g[1:], ""
    else:
        prefix = "" if "/" in g else "(?:.*/)?"  # 不带斜杠:任意层
    out, i = prefix, 0
    while i < len(g):
        c = g[i]
        seg_start = i == 0 or g[i - 1] == "/"
        if g.startswith("**", i) and seg_start and (i + 2 == len(g) or g[i + 2] == "/"):
            if i + 2 == len(g):
                out += ".*"
                i += 2
            else:
                out += "(?:.*/)?"
                i += 3
            continue
        if c == "*":
            while i < len(g) and g[i] == "*":
                i += 1
            out += "[^/]*"
            continue
        if c == "?":
            out += "[^/]"
        elif c == "[":
            cls, i = _bracket(g, i)
            out += cls
            continue
        elif c == "\\":
            if i + 1 >= len(g):
                raise ValueError("glob %r: trailing backslash" % g)
            out += re.escape(g[i + 1])
            i += 2
            continue
        else:
            out += re.escape(c)
        i += 1
    return out


def compile(g):
    """glob -> 编译好的正则(fullmatch 用);不支持的写法 ValueError。"""
    return re.compile("(?:%s)\\Z" % "|".join(_one(x) for x in expand(g.strip())))


def check(g):
    """不支持就 ValueError,支持就返回 None(只校验)。"""
    compile(g)


def matcher(globs):
    """[glob] -> 判断一个相对路径是否匹配其中任一个的函数。"""
    rxs = [compile(g) for g in globs]
    return lambda path: any(rx.match(path) for rx in rxs)
