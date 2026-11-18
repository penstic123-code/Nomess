"""内置文件清单与依赖(给 nomess map / check 用)。文件清单取 git 已跟踪加未忽略的新文件,天然排除生成物;
依赖只留仓库内部的,按扩展名认语言:Python / JS·TS / C·C++ / Go / Rust / C#。Python 用 ast,其余正则级(注释、字符串里的也会算)。
每个文件的原始 import 和头注释第一句经 cache.facts 缓存;落到哪个文件(边)每次现算。"""
import ast
import os
import posixpath
import re
import warnings

import cache
import snapshot

EXT_LANG = {".py": "py", ".js": "js", ".jsx": "js", ".mjs": "js", ".ts": "js", ".tsx": "js",
            ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c", ".hpp": "c", ".cxx": "c",
            ".go": "go", ".rs": "rs", ".cs": "cs"}
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs")
VERSION = "1"  # 缓存事实(import、头注释)的提取写法版本,改了就加一


def all_files(snap):
    """快照里的全部普通文件(相对仓库根的正斜杠路径),任何扩展名。工作区快照 = git 管着加未忽略的新文件,天然排除生成物。"""
    return sorted(p for p, m in snap.files().items() if m in snapshot.REGULAR)


def sources(names):
    """names 里的源文件(扩展名在 EXT_LANG 里的)。"""
    return [n for n in names if os.path.splitext(n)[1] in EXT_LANG]


def tracked(snap):
    return sources(all_files(snap))


def _sentence(s):
    s = s.strip()
    m = re.search(r"。|\.(?:\s|$)", s)
    if m:
        s = s[:m.start() + (1 if s[m.start()] == "。" else 0)]
    return s[:80].strip()


def _head(snap, rel):
    """[头注释第一句 | None, 文件是否为空];经 cache.facts 缓存(kind deps.header.py / deps.header.other,头注释写法看是不是 .py)。"""
    py = rel.endswith(".py")
    return cache.facts(snap, rel, "deps.header." + ("py" if py else "other"), VERSION, lambda text: [_header(text, py), text == ""])


def header(snap, rel):
    """头注释第一句;没有返回 None。"""
    return _head(snap, rel)[0]


def missing_header(snap, rel):
    """非空文件没有头注释(HDR 用)。"""
    h, empty = _head(snap, rel)
    return h is None and not empty


def _header(text, py):
    raw = text[:2048].lstrip("\ufeff").split("\n")
    lines = [l.strip() for l in raw if l.strip() and not l.startswith("#!") and not re.match(r"#.*coding[:=]", l)]
    if not lines:
        return None
    first = lines[0]
    if py:
        for q in ('"""', "'''"):
            if first.startswith(q):
                rest = first[3:].replace(q, "")
                return _sentence(rest or (lines[1] if len(lines) > 1 else "")) or None
        return (_sentence(first.lstrip("#")) or None) if first.startswith("#") else None
    if first.startswith("//"):
        return _sentence(first.lstrip("/")) or None
    if first.startswith("/*"):
        rest = first[2:].replace("*/", "").lstrip("*!")
        if not rest.strip() and len(lines) > 1:
            rest = lines[1].lstrip("*").replace("*/", "")
        return _sentence(rest) or None
    return None


# ---------------------------------------------------------------- 原始事实:每个文件里还没解析的 import(单文件可得,经 cache.facts 缓存)
# 键里的 kind 带语言(deps.<语言>),VERSION 改了提取写法就加一(头注释的 deps.header.* 也用它)。落到哪个文件(边)要看整棵树,每次现算、不进缓存。


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _raw_py(text):
    """[[前导点数, 模块, [导入的名字], 行]]:用 ast,文档字符串和注释里的 import 不算;语法错误的文件没有 import 事实。"""
    try:
        with warnings.catch_warnings():  # 被查文件里的无效转义等只该由它自己的工具报,不混进 nomess 的输出
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [[0, a.name, [], n.lineno] for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            out.append([n.level, n.module or "", [a.name for a in n.names if a.name != "*"], n.lineno])
    return sorted(out)


def _raw_js(text):
    return [[m.group(1), _line(text, m.start())]
            for m in re.finditer(r"""(?:from|import|require)\s*\(?\s*['"](\.[^'"]*)['"]""", text)]


def _raw_c(text):
    return [[m.group(1), _line(text, m.start())] for m in re.finditer(r'^[ \t]*#[ \t]*include[ \t]*"([^"]+)"', text, re.M)]


def _raw_go(text):
    out = [[m.group(1), _line(text, m.start())] for m in re.finditer(r'^[ \t]*import[ \t]+(?:\w+[ \t]+)?"([^"]+)"', text, re.M)]
    for blk in re.finditer(r"^[ \t]*import[ \t]*\((.*?)\)", text, re.M | re.S):
        out += [[m.group(1), _line(text, blk.start(1) + m.start())] for m in re.finditer(r'"([^"]+)"', blk.group(1))]
    return out


def _raw_rs(text):
    return {"mod": [[m.group(1), _line(text, m.start())]
                    for m in re.finditer(r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?mod[ \t]+(\w+)[ \t]*;", text, re.M)],
            "use": [[m.group(1), _line(text, m.start())]
                    for m in re.finditer(r"^[ \t]*(?:pub[ \t]+)?use[ \t]+crate::([\w:]+)", text, re.M)]}


def _raw_cs(text):
    return {"ns": sorted({m.group(1) for m in re.finditer(r"^[ \t]*namespace[ \t]+([\w.]+)", text, re.M)}),
            "using": [[m.group(1), _line(text, m.start())]
                      for m in re.finditer(r"^[ \t]*using[ \t]+(?:static[ \t]+)?([\w.]+)[ \t]*;", text, re.M)]}


RAW = {"py": _raw_py, "js": _raw_js, "c": _raw_c, "go": _raw_go, "rs": _raw_rs, "cs": _raw_cs}


def raw(snap, path):
    """path 的原始 import 事实(形状见各 _raw_*);经缓存,按内容对象名命中。"""
    lang = EXT_LANG[os.path.splitext(path)[1]]
    return cache.facts(snap, path, "deps." + lang, VERSION, RAW[lang])


# ---------------------------------------------------------------- 解析:import -> 仓库内文件(每次现算)

def _norm(p):
    return posixpath.normpath(p)


def _py(src, imps, fs):
    out = {}
    d0 = posixpath.dirname(src)
    for dots, mod, names, line in imps:
        dirs = [_norm(posixpath.join(d0, *([".."] * (dots - 1))))] if dots else [d0, ""]
        for d in dirs:
            hits = set()
            path = _norm(posixpath.join(d, mod.replace(".", "/"))) if mod else d
            path = "" if path == "." else path
            for cand in (path + ".py", posixpath.join(path, "__init__.py")):
                if cand in fs and mod:
                    hits.add(cand)
            for n in names:
                for cand in (posixpath.join(path, n + ".py"), posixpath.join(path, n, "__init__.py")):
                    if cand in fs:
                        hits.add(cand)
            if hits:
                for h in hits:
                    out.setdefault(h, line)
                break
    return out


def _js(src, imps, fs):
    out = {}
    for spec, line in imps:
        p = _norm(posixpath.join(posixpath.dirname(src), spec))
        root, ext = posixpath.splitext(p)
        cands = [p] + [p + e for e in JS_EXT] + [posixpath.join(p, "index" + e) for e in JS_EXT]
        if ext in (".js", ".jsx", ".mjs"):
            cands += [root + e for e in (".ts", ".tsx")]
        for c in cands:
            if c in fs:
                out.setdefault(c, line)
                break
    return out


def _c(src, imps, fs, by_name):
    out = {}
    for inc, line in imps:
        for c in (_norm(posixpath.join(posixpath.dirname(src), inc)), _norm(inc)):
            if c in fs:
                out.setdefault(c, line)
                break
        else:
            hits = [f for f in by_name.get(posixpath.basename(inc), []) if f.endswith("/" + inc)]
            if len(hits) == 1:
                out.setdefault(hits[0], line)
    return out


def _go(imps, mod, by_dir):
    out = {}
    for i, line in imps:
        if mod and (i == mod or i.startswith(mod + "/")):
            d = i[len(mod):].lstrip("/")
            for f in by_dir.get(d, []):
                if f.endswith(".go") and not f.endswith("_test.go"):
                    out.setdefault(f, line)
    return out


def _rs(src, imps, fs):
    out = {}
    stem = posixpath.splitext(posixpath.basename(src))[0]
    d0 = posixpath.dirname(src)
    mdir = d0 if stem in ("mod", "lib", "main") else posixpath.join(d0, stem)
    for name, line in imps["mod"]:
        for c in (posixpath.join(mdir, name + ".rs"), posixpath.join(mdir, name, "mod.rs")):
            if _norm(c) in fs:
                out.setdefault(_norm(c), line)
                break
    parts = src.split("/")[:-1]
    root = "/".join(parts[:len(parts) - parts[::-1].index("src")]) if "src" in parts else ""
    for path, line in imps["use"]:
        d, found = root, None
        for part in path.split("::"):
            for c in (posixpath.join(d, part + ".rs"), posixpath.join(d, part, "mod.rs")):
                if _norm(c) in fs:
                    found = _norm(c)
                    break
            else:
                break
            d = posixpath.join(d, part)
        if found:
            out.setdefault(found, line)
    return out


def edges(snap, files=None):
    """{(源文件, 被依赖文件): 行号(第一处)};不含自环。原始 import 经缓存,落到哪个文件每次按 files 现算。"""
    files = files or tracked(snap)
    fs = set(files)
    by_name, by_dir = {}, {}
    for f in files:
        by_name.setdefault(posixpath.basename(f), []).append(f)
        by_dir.setdefault(posixpath.dirname(f), []).append(f)
    gomod = None
    if snap.isfile("go.mod"):
        m = re.search(r"^module[ \t]+(\S+)", snap.text("go.mod"), re.M)
        gomod = m.group(1) if m else None
    facts = {f: raw(snap, f) for f in files}
    ns = {}
    for f in files:
        if f.endswith(".cs"):
            for n in facts[f]["ns"]:
                ns.setdefault(n, set()).add(f)
    out = {}
    for f in files:
        lang, imps = EXT_LANG[os.path.splitext(f)[1]], facts[f]
        if lang == "py":
            hit = _py(f, imps, fs)
        elif lang == "js":
            hit = _js(f, imps, fs)
        elif lang == "c":
            hit = _c(f, imps, fs, by_name)
        elif lang == "go":
            hit = _go(imps, gomod, by_dir)
        elif lang == "rs":
            hit = _rs(f, imps, fs)
        else:
            hit = {}
            for name, line in imps["using"]:
                for x in ns.get(name, ()):
                    hit.setdefault(x, line)
        for x, line in hit.items():
            if x != f:
                out[(f, x)] = line
    return out
