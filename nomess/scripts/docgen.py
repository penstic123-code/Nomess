"""文档生成段:把文件里 <!-- GEN:<名字> BEGIN --> 与 <!-- GEN:<名字> END --> 之间的内容交给登记的生成器重写。
标记之间只能由生成器写,手改会被下一次生成盖掉;标记之外是手写的,不动。一段的两个标记各占一行,同名标记在一个文件里只许一对。
加一个生成段 = 在目标文件里放一对标记 + 在 nomess.json 的 "docgen" 段加一行。
生成器四选一:map(抽取表名)、cmd(标准输出即正文,须输出 UTF-8,超时缺省 60 秒)、py("文件:函数")、builtin(见 builtin.py)。
"""
import contextlib
import importlib.util
import os
import re
import subprocess
import sys

import nm_config
import outwrite
import snapshot
from messages import t


def markers(name):
    return "<!-- GEN:%s BEGIN -->" % name, "<!-- GEN:%s END -->" % name


def _span(text, name, path):
    """(正文起点, 正文终点):BEGIN 行之后到 END 行之前。标记缺失、重复、顺序不对就报错。"""
    b, e = markers(name)
    bs = [m.end() for m in re.finditer("^" + re.escape(b) + "[ \t]*(?=\r?$)", text, re.M)]
    es = [m.start() for m in re.finditer("^" + re.escape(e) + "[ \t]*(?=\r?$)", text, re.M)]
    if len(bs) != 1 or len(es) != 1 or bs[0] > es[0]:
        raise ValueError(t("GEN_MARKERS", path, name, len(bs), len(es)))
    return bs[0], es[0]


def read_section(text, name, path):
    a, b = _span(text, name, path)
    return text[a:b]


_BEGIN = re.compile(r"<!-- GEN:(.+?) BEGIN -->[ \t]*")


def gen_ranges(text):
    """文本里所有生成段的行范围 [(起行, 止行)](行号从 1 起,含 BEGIN、END 标记行);只收 BEGIN 和同名 END 配上的段。"""
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for i, l in enumerate(lines):
        m = _BEGIN.fullmatch(l)
        if m:
            end = markers(m.group(1))[1]
            j = next((k for k in range(i + 1, len(lines)) if lines[k].rstrip(" \t") == end), None)
            if j is not None:
                out.append((i + 1, j + 1))
    return out


def same(a, b):
    norm = lambda s: s.replace("\r\n", "\n").strip("\n")
    return norm(a) == norm(b)


def replace_section(text, name, body, path):
    """text 里 name 段换成 body;标记之外的字节一个都不改。"""
    a, b = _span(text, name, path)
    eol = "\r\n" if text[a:a + 1] == "\r" else "\n"  # 沿用 BEGIN 标记行的换行
    new = eol + body.replace("\r\n", "\n").strip("\n").replace("\n", eol) + eol
    return text[:a] + new + text[b:]


def _load_py(base, ref):
    path, _, func = ref.partition(":")
    path = os.path.normpath(os.path.join(base, path))
    mod_name = os.path.splitext(os.path.basename(path))[0]
    mod = sys.modules.get(mod_name)
    if mod is None or os.path.normcase(os.path.abspath(getattr(mod, "__file__", ""))) != os.path.normcase(path):
        sys.path.insert(0, os.path.dirname(path))
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    return getattr(mod, func)


def sections_of(cfg):
    secs = cfg.get("docgen", {})
    for name, spec in secs.items():
        if "file" not in spec or sum(k in spec for k in ("py", "cmd", "map", "builtin")) != 1:
            raise ValueError(t("GEN_SPEC", name))
    return secs


def produce(snap, cfg, spec):
    base = snap.root  # cmd / py 生成器在工作区里跑、读磁盘(不走快照)
    if "py" in spec:
        with contextlib.redirect_stdout(sys.stderr):  # 正文是返回值;生成器顺手 print 的不能混进 stdout(--json 模式 stdout 只许有 JSON)
            return _load_py(base, spec["py"])()
    if "map" in spec:
        import map as nm_map
        return nm_map.generate(snap, cfg, spec["map"])
    if "builtin" in spec:
        import builtin
        return builtin.produce(snap, cfg, spec)
    # 子进程输出统一 UTF-8:Python 子进程靠环境变量,其他工具要自己输出 UTF-8;解码失败就报错,不替换
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run(spec["cmd"], cwd=base, capture_output=True, encoding="utf-8", env=env, timeout=spec.get("timeout", 60))
    if r.returncode != 0:
        last = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-1:] or [t("GEN_NO_OUT")]
        raise ValueError(t("GEN_FAILED", spec["cmd"], r.returncode, last[0]))
    return r.stdout


def run(snap, cfg, names=None, exec_=True):
    """按快照算生成段:返回 (过时的 [(名字, 文件)], {文件: 换好段的完整新内容 bytes})。不写盘。
    exec_ 为假时跳过 cmd / py 生成器(它们会执行项目代码)。"""
    import builtin
    sections = sections_of(cfg)
    bad = [n for n in names or [] if n not in sections]
    if bad:
        raise KeyError(t("GEN_UNKNOWN", ", ".join(bad), ", ".join(sections)))
    stale, puts = [], {}
    for name in names or sections:
        if not exec_ and ("cmd" in sections[name] or "py" in sections[name]):
            continue
        spec = sections[name]
        if "builtin" in spec and spec["builtin"] not in builtin.GENERATORS:
            print(t("GEN_SKIP_BUILTIN", name, spec["builtin"]), file=sys.stderr)  # 旧配置里的内置生成器已不存在:提示并跳过,不拦提交
            continue
        rel = sections[name]["file"]
        text = puts.get(rel)
        if text is None:
            text = snap.text(rel)
            if text is None:
                raise ValueError(t("GEN_NO_FILE", rel, name))
        body = produce(snap, cfg, sections[name])
        if not same(read_section(text, name, rel), body):
            stale.append((name, rel))
            puts[rel] = replace_section(text, name, body, rel)
    return stale, {rel: text.encode("utf-8") for rel, text in puts.items()}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess docgen", description="rewrite the generated doc sections; files are not touched when nothing changed")
    ap.add_argument("names", nargs="*", help="only these sections (default: all)")
    ap.add_argument("--check", action="store_true", help="compare only, do not write; exit 1 if any section is stale")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    with snapshot.open_snapshot(os.path.dirname(config), "worktree") as snap:
        stale, puts = run(snap, nm_config.load(config), a.names)
    if not a.check:
        outwrite.apply(os.path.dirname(config), puts)
    for name, f in stale:
        print("%s %s (%s)" % (t("STALE") if a.check else t("REWRITTEN"), name, f))
    return 1 if a.check and stale else 0
