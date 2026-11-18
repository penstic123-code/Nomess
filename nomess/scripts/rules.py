"""按路径加载的规则文件:从教训条目和系统页“坑”段里带 `路径:` 和 `规则:` 的条目生成 .claude/rules/nomess/<标识>.md。
规则文件只是条目的视图,全部生成、不手改;一个事实只有一个家(那条教训 / 那条坑)。  nomess rules [--check]
条目:教训库里除 inbox 外各页的 `## 标题`,和 docs/systems/*.md 里 `## 坑`(或 `## Pitfalls`)段下的 `### 标题`;
  键同教训条目(见 lessons.py),这里用 `路径:`(逗号分隔的 glob,花括号里的逗号不算)和 `规则:`(一句话,中文 40 字 / 英文 25 词内)。
  只有状态明确是已核实、路径和规则都写了、glob 都支持的才生成。
归类:路径集合相同的条目进同一个文件,文件的 paths 就是条目自己写的 glob(不扩大适用范围);文件名是这组 glob 的哈希前 8 位
  (稳定,只含小写十六进制:不会撞大小写,也不会是 Windows 设备名)。glob 语义见 pathglob.py(对齐 Claude Code)。
写入前确认输出目录和每个要写、要删的文件都不经过符号链接 / junction。
check 报:RUL1 红 规则文件 frontmatter 不是生成的格式(解析失败的规则会变成常驻加载);黄 RUL2 过时,RUL3 超预算(rules.file_tokens,缺省 400),
  RUL4 glob 一个文件都匹不到,RUL5 条目只写了路径或规则之一 / 状态不是已核实 / glob 不支持 / 规则太长。
"""
import hashlib
import json
import os
import re

import deps
import docgen
import lessons
import nm_config
import outwrite
import pathglob
import posixpath
import snapshot
from messages import t
from nm_config import F, est_tokens

RULES_DIR = ".claude/rules/nomess"
FILE_TOKENS = 400
PITFALLS = re.compile(r"^##[ \t]+(坑|Pitfalls)[ \t]*$")
CJK = re.compile(r"[㐀-鿿]")


def pitfalls(text, name):
    """系统页“坑”段里的条目(### 标题 + 键行),行号是整页的;代码围栏里的标题不算。"""
    lines = lessons.text_lines(text)
    fenced = lessons.in_fence(lines)
    heads = [i for i, l in enumerate(lines) if not fenced[i] and l.startswith("## ")]
    start = next((i for i in heads if PITFALLS.match(lines[i])), None)
    if start is None:
        return []
    end = next((i for i in heads if i > start), len(lines))
    es = lessons.parse_lines(lines[start + 1:end], name, head="### ")
    for e in es:
        e["line"] += start + 1
        e["end"] += start + 1
    return es


def entries(snap, cfg):
    """[(相对项目根的文件, 条目)]:教训库(不含 inbox)和系统页“坑”段里所有条目,按文件、行号排。"""
    out = []
    ldir = cfg.get("lessons_dir", "docs/lessons")
    for p in snap.ls(ldir, ".md"):
        if posixpath.basename(p) != lessons.INBOX:
            out += [(p, e) for e in lessons.parse_text(snap.text(p), posixpath.basename(p))]
    for p in snap.ls("docs/systems", ".md"):
        out += [(p, e) for e in pitfalls(snap.text(p), posixpath.basename(p))]
    return out


def why_not(e):
    """条目为什么不生成规则:None = 生成;"skip" = 本来就不生成(路径和规则都没写);
    其余要提示:"half" 只写了一个,"unverified" 状态不是已核实,"glob" 有不支持的 glob。"""
    if not (e["paths"] or e["rule"]):
        return "skip"
    if not (e["paths"] and e["rule"] and pathglob.split_globs(e["paths"])):
        return "half"
    if not e["verified"]:
        return "unverified"
    try:
        for g in pathglob.split_globs(e["paths"]):
            pathglob.check(g)
    except ValueError:
        return "glob"
    return None


def render(paths, lines):
    if not paths or not all(p.strip() for p in paths):
        raise ValueError(t("FM_START"))  # 没有 paths 的规则文件会被当成常驻规则,绝不写出
    head = ["---", "paths:"] + ["  - " + json.dumps(p, ensure_ascii=False) for p in paths] + ["---", t("RULES_HEADER")]
    return "\n".join(head + lines) + "\n"


def generate(snap, cfg, es):
    """({相对项目根的路径: 内容}, [(条目, 匹不到文件的 glob)])。es 是 entries() 的结果。"""
    names = deps.all_files(snap)
    groups, dead = {}, []
    for rel, e in es:
        if why_not(e):
            continue
        globs = tuple(sorted(set(pathglob.split_globs(e["paths"]))))
        groups.setdefault(globs, set()).add("- %s → %s#%s" % (e["rule"], rel, e["title"]))
        dead += [(dict(e, file=rel), g) for g in pathglob.split_globs(e["paths"]) if not any(map(pathglob.compile(g).match, names))]
    out = {}
    for globs, lines in groups.items():
        rel = "%s/%s.md" % (RULES_DIR, hashlib.sha1("\n".join(globs).encode("utf-8")).hexdigest()[:8])
        if rel in out:
            raise ValueError("rules file name clash: %s" % rel)
        out[rel] = render(globs, sorted(lines))
    return dict(sorted(out.items())), dead


def on_disk(snap):
    return snap.ls(RULES_DIR, ".md", recursive=True)


def plan(snap, cfg):
    """{路径: 新内容 bytes | None(删多余的旧文件)}:生成结果和快照比,只含要改的。不写盘(落盘走 outwrite.apply)。"""
    new, _ = generate(snap, cfg, entries(snap, cfg))
    return _diff(snap, new)


def _diff(snap, new):
    out = {rel: tx.encode("utf-8") for rel, tx in new.items() if snap.text(rel) is None or not docgen.same(snap.text(rel), tx)}
    out.update(dict.fromkeys(rel for rel in on_disk(snap) if rel not in new))
    return out


def parse_frontmatter(text):
    """规则文件的 paths 列表;格式必须就是 render 写的那样,否则 ValueError。"""
    lines = text.replace("\r\n", "\n").split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if lines[0] != "---" or end is None or end < 3 or lines[1] != "paths:":
        raise ValueError(t("FM_START"))
    out = []
    for l in lines[2:end]:
        m = re.fullmatch(r'  - (".+")', l)
        if not m:
            raise ValueError(t("FM_LINE", l))
        out.append(json.loads(m.group(1)))
    return out


def broken_frontmatter(snap):
    """RUL1(红):规则文件的 frontmatter 写错。"""
    out = []
    for rel in on_disk(snap):
        try:
            parse_frontmatter(snap.text(rel))
        except ValueError as e:
            out.append(F("red", "RUL1", rel, 1, "frontmatter", t("RUL1", e)))
    return out


def findings(snap, cfg):
    """RUL2–RUL5(黄)。条目和生成结果各只算一次。"""
    budget = cfg.get("rules", {}).get("file_tokens", FILE_TOKENS)
    es = entries(snap, cfg)
    new, dead = generate(snap, cfg, es)
    out = [F("yellow", "RUL2", rel, 0, "stale", t("RUL2")) for rel in _diff(snap, new)]
    out += [F("yellow", "RUL3", rel, 0, "big", t("RUL3", est_tokens(tx), budget))
            for rel, tx in new.items() if est_tokens(tx) > budget]
    out += [F("yellow", "RUL4", e["file"], e["line"], gl, t("RUL4", e["title"], gl)) for e, gl in dead]
    for rel, e in es:
        why = why_not(e)
        if why in ("half", "unverified", "glob"):
            out.append(F("yellow", "RUL5", rel, e["line"], e["title"], t("RUL5_" + why.upper(), e["title"])))
        elif why is None and (len(e["rule"]) > 40 if CJK.search(e["rule"]) else len(e["rule"].split()) > 25):
            out.append(F("yellow", "RUL5", rel, e["line"], e["title"], t("RUL5_LONG", e["title"])))
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess rules", description="generate the path-scoped rules files under .claude/rules/nomess/")
    ap.add_argument("--check", action="store_true", help="compare only, do not write; exit 1 if any file is stale")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    base = os.path.dirname(config)
    with snapshot.open_snapshot(base, "worktree") as snap:
        changed = plan(snap, nm_config.load(config))
    if not a.check:
        outwrite.apply(base, changed)
        outwrite.prune_empty(base, RULES_DIR)
    for rel in changed:
        print("%s %s" % (t("STALE") if a.check else t("WRITTEN"), rel))
    return 1 if a.check and changed else 0
