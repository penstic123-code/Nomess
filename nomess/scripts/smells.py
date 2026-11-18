"""按文件的屎山检测:P1 吞异常、P2 补丁和待办注释、P5 _v2/_old 类名字、S1 文件过长、S2 函数过长(只有 Python)。
每个文件的原始事实(行数、标签数、定义的标识符、函数起止、except 块、空 catch)经 cache.facts 缓存,kind = smells.<语言>;
阈值、开关、"新增"(对比基线)都不在缓存里:这里只报"找到了什么",颜色之外的判定由 check 统一做。"""
import ast
import os
import re

import cache
import clones
import deps
import nm_config
from messages import add, t

ANALYZER = 1  # 改提取逻辑就加一,旧缓存整批作废
M = {
    "SM_P1_WHAT": ("swallowed exception", "吞掉的异常"),
    "SM_P1_WHY": ("An empty handler hides failures; handle it, narrow it, or let it propagate", "空的处理体会把失败藏起来;处理掉、收窄类型,或者让它抛出去"),
    "SM_P2_WHAT": ("patch and to-do comments", "补丁和待办注释"),
    "SM_P2_WHY": ("Each one is a shortcut someone meant to undo; fix or record it", "每一处都是打算以后撤销的捷径;修掉,或记进方案"),
    "SM_P5_WHAT": ("_v2 / _old style name", "_v2 / _old 类的名字"),
    "SM_P5_WHY": ("A second copy beside the old one means two implementations; replace the old one", "旧的旁边再放一个就是两套实现;直接替换旧的"),
    "SM_S1_WHAT": ("file too long", "文件过长"),
    "SM_S1_WHY": ("A long file cannot be read whole; split it by responsibility", "太长的文件没法整读;按职责拆开"),
    "SM_S2_WHAT": ("function too long", "函数过长"),
    "SM_S2_WHY": ("A long function does several things; split it", "太长的函数干了好几件事;拆开"),
    "SM_P1_ALL": ("`except` catches everything and does nothing", "`except` 抓了全部异常却什么都不做"),
    "SM_P1_ONE": ("`except %s` is swallowed", "`except %s` 被吞掉了"),
    "SM_P1_JS": ("empty catch block", "空的 catch"),
    "SM_P2": ("%d patch or to-do marker(s) (%s)", "%d 处补丁或待办标记(%s)"),
    "SM_P5_NAME": ("new name `%s` ends like a second version", "新名字 `%s` 的结尾像第二版"),
    "SM_P5_FILE": ("file name ends like a second version", "文件名的结尾像第二版"),
    "SM_S1": ("%d non-empty lines (limit %d)", "%d 个非空行(上限 %d)"),
    "SM_S2": ("`%s` is %d lines (limit %d)", "`%s` 有 %d 行(上限 %d)"),
}
add(M)
RULES = [{"id": i, "level": lv, "what": "SM_%s_WHAT" % i, "why": "SM_%s_WHY" % i}
         for i, lv in (("P1", "red"), ("P2", "yellow"), ("P5", "yellow"), ("S1", "red"), ("S2", "red"))]
IDS = frozenset(r["id"] for r in RULES)

_TAGS = [re.compile(p, f) for p, f in (
    (r"\b(hack|workaround|temporary|temp fix|quick fix|kludge)\b", re.I), (r"\b(TODO|FIXME|XXX)\b", 0),
    (r"(临时|先这样|绕过|兼容旧)", 0))]
_DECL = re.compile(r"\b(?:function|class|const|let|var|def|fn|func|struct|enum|interface|type)\s+([A-Za-z_$][\w$]*)")
_SUFFIX = (re.compile(r"[_\-.](?:v\d+|new|old|fixed|tmp|copy|bak)$", re.I), re.compile(r"(?<=[a-z0-9])(?:V\d+|New|Old|Fixed|Tmp|Copy|Bak)$"))
_FILE_EXT = {".bak", ".old", ".tmp"}
_ALL = {"Exception", "BaseException"}


def lang(path):
    return {"py": "py", "js": "js"}.get(deps.EXT_LANG.get(os.path.splitext(path)[1]), "other")


def _swallows(body):
    return all(isinstance(s, (ast.Pass, ast.Continue)) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                                          and s.value.value is Ellipsis) for s in body)


def _catches_all(t_):
    if t_ is None:
        return True
    elts = t_.elts if isinstance(t_, ast.Tuple) else [t_]
    return any(isinstance(e, ast.Name) and e.id in _ALL for e in elts)


def _py(text):
    """{"funcs": [[全名, 起, 止]], "excepts": [[行, 抓全部, 处理体只有 pass / ... / continue, 抓的类型文本]], "names": [[名字, 行]]};语法错误全空。"""
    out = {"funcs": [], "excepts": [], "names": []}
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return out

    def walk(node, prefix):
        scope = isinstance(node, (ast.Module, ast.ClassDef))
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = prefix + ch.name
                out["names"].append([ch.name, ch.lineno])
                if not isinstance(ch, ast.ClassDef):
                    out["funcs"].append([q, ch.lineno, ch.end_lineno])
                walk(ch, q + ".")
                continue
            if isinstance(ch, ast.ExceptHandler):
                out["excepts"].append([ch.lineno, _catches_all(ch.type), _swallows(ch.body),
                                       ast.unparse(ch.type) if ch.type is not None else ""])
            elif scope and isinstance(ch, (ast.Assign, ast.AnnAssign)):
                for tg in (ch.targets if isinstance(ch, ast.Assign) else [ch.target]):
                    if isinstance(tg, ast.Name):
                        out["names"].append([tg.id, ch.lineno])
            walk(ch, prefix)

    walk(tree, "")
    return out


def _skip_parens(tok, j):
    """tok[j] 是 "(" -> 配对的 ")" 之后的位置。"""
    depth = 0
    while j < len(tok):
        depth += tok[j] == "("
        depth -= tok[j] == ")"
        j += 1
        if depth == 0:
            break
    return j


def _js_catches(text):
    """空的 catch 块和 .catch(() => {}) 的行号(去掉注释后看 token:里面写了注释也算空)。"""
    tok, _, ln = clones.tokenize(text, "c")
    out = []
    for i, x in enumerate(tok):
        if x != "catch":
            continue
        if i and tok[i - 1] == ".":
            j = i + 2  # .catch( 之后
            if tok[j:j + 1] == ["("]:
                j = _skip_parens(tok, j)
            else:
                j += 1
            if tok[j:j + 5] == ["=", ">", "{", "}", ")"]:
                out.append(ln[i])
        else:
            j = _skip_parens(tok, i + 1) if tok[i + 1:i + 2] == ["("] else i + 1
            if tok[j:j + 2] == ["{", "}"]:
                out.append(ln[i])
    return out


def _facts(text, lg):
    lines = text.split("\n")
    out = {"lines": sum(1 for x in lines if x.strip()),
           "tags": {}}
    for rx in _TAGS:
        for m in rx.finditer(text):
            out["tags"][m.group(0).lower()] = out["tags"].get(m.group(0).lower(), 0) + 1
    if lg == "py":
        out.update(_py(text))
    else:
        out["names"] = [[m.group(1), text.count("\n", 0, m.start()) + 1] for m in _DECL.finditer(text)]
        if lg == "js":
            out["catches"] = _js_catches(text)
    return out


def _second_version(name):
    return any(rx.search(name) for rx in _SUFFIX)


def _file_p5(path):
    stem, ext = os.path.splitext(os.path.basename(path))
    return _second_version(stem) or ext.lower() in _FILE_EXT


def run(snap, changes, eff):
    out = []
    for p in sorted(changes):
        if changes[p] == "D":
            continue
        e = eff(p)
        on = e["checks"] & IDS
        if not on:
            continue
        if "P5" in on and _file_p5(p):
            out.append(nm_config.F("yellow", "P5", p, 0, p, t("SM_P5_FILE"), k=["@file"]))
        ext = os.path.splitext(p)[1]
        if ext not in deps.EXT_LANG and ext not in e["smells"]["extra_ext"]:  # 扩展名资格按这个文件的有效配置判
            continue
        lg = lang(p)
        f = cache.facts(snap, p, "smells." + lg, ANALYZER, lambda s, lg=lg: _facts(s, lg))
        if f is None:
            continue
        sm = e["smells"]
        if "S1" in on and f["lines"] > sm["file_lines"]:
            out.append(nm_config.F("red", "S1", p, 0, p, t("SM_S1", f["lines"], sm["file_lines"]), k=[], metric=f["lines"]))
        if "S2" in on:
            seen = {}
            for q, a, b in f.get("funcs", ()):
                n = b - a + 1
                seen[q] = seen.get(q, 0) + 1
                if n > sm["func_lines"]:
                    out.append(nm_config.F("red", "S2", p, a, q, t("SM_S2", q, n, sm["func_lines"]),
                                           k=[q if seen[q] == 1 else "%s#%d" % (q, seen[q])], metric=n))
        if "P1" in on:
            for line, all_, swallow, typ in f.get("excepts", ()):
                if swallow:
                    out.append(nm_config.F("red" if all_ else "yellow", "P1", p, line, "except " + typ if typ else "except",
                                           t("SM_P1_ALL") if all_ else t("SM_P1_ONE", typ), k=[]))
            for line in f.get("catches", ()):
                out.append(nm_config.F("yellow", "P1", p, line, "catch", t("SM_P1_JS"), k=[]))
        if "P2" in on and f["tags"]:
            n = sum(f["tags"].values())
            out.append(nm_config.F("yellow", "P2", p, 0, p, t("SM_P2", n, ", ".join(sorted(f["tags"]))), k=[], metric=n))
        if "P5" in on:
            for name, line in f["names"]:
                if _second_version(name):
                    out.append(nm_config.F("yellow", "P5", p, line, name, t("SM_P5_NAME", name), k=[name]))
    return out
