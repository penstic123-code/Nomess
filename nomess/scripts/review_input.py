"""nomess review-input <基准> [片段文件]:审查者的全部输入(零 token,子代理和 review.cmd 用同一份)。基准 = 提交号或分支名。
顺序写死:第一行审查档(review.level;有必审项时行末加 [must-review])→ 必审(新增 allow、新冻结的规则号、被放宽的基线和配置)→
新增的红黄项(存量不列)→ diff 涉及文件命中的教训标题(教训的 `路径:` 匹配改动文件)→ diff → 片段文件(相关的设计片段,原样)。
检查结果取 check.evaluate(HEAD 的树, 基准的树, exec_cmd=False):不跑项目里的任何代码。
--cmd:把审查清单 + 上面这份输入从标准输入交给 nomess.json 的 review.cmd(argv 数组,不经 shell),打印它的输出;非零退出或超过 600 秒报错,不当"没发现问题"。"""
import json
import os
import re
import subprocess

import check
import lessons
import messages
import nm_config
import pathglob
import rules as nm_rules
import snapshot
from messages import name as nm_name, t

M = {
    "RI_DOCTYPE": ("new doc_types entry: %s", "新增 doc_types 条目:%s"),
    "RI_L6_SRC": ("L6 external-source lesson %r lost its source line", "L6 外部来源的教训 %r 被去掉了来源行"),
    "RI_L6_OK": ("L6 external-source lesson %r was changed to verified", "L6 外部来源的教训 %r 的状态被改成已核实"),
}
messages.add(M)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess review-input", description="everything a reviewer needs for HEAD against a base: review level, must-review items, new findings, related lessons, diff")
    ap.add_argument("base", help="base commit or branch (the trusted side of the diff)")
    ap.add_argument("fragment", nargs="?", help="a file with the relevant design fragment, appended unchanged at the end")
    ap.add_argument("--cmd", action="store_true", help="pipe the checklist and this input to review.cmd from nomess.json and print its output")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    root = os.path.dirname(config)
    with snapshot.open_snapshot(root, "tree", "HEAD") as cand, snapshot.open_snapshot(root, "tree", a.base) as base:
        res = check.evaluate(cand, base, exec_cmd=False)
        if res["skipped"]:
            print(res["skipped"])
            return 0
        diff = cand.diff(base)
        btext = base.text(nm_config.CONFIG_NAME)
        bexp = nm_config.expanded(nm_config.parse(btext, nm_config.CONFIG_NAME) if btext else {})
        cfg = nm_config.parse(cand.text(nm_config.CONFIG_NAME), nm_config.CONFIG_NAME)  # 后解析待检的:提示语按它的 lang
        exp = nm_config.expanded(cfg)
        entries = lessons.snapshot_entries(cand, exp["lessons_dir"])
        new_types = [x for x in exp["doc_types"] if x not in bexp["doc_types"]]
        l6 = _l6(base, bexp["lessons_dir"], cand, exp["lessons_dir"])
    if not diff:
        print(t("RI_EMPTY"))
        return 0
    out = []
    rv = res["review"]
    must = [t("RI_ALLOW", json.dumps(x, ensure_ascii=False)) for x in res["new_allow"]]
    must += [t("RI_FROZEN", r) for r in res["new_frozen"]]
    must += [t("RI_DOCTYPE", json.dumps(x, ensure_ascii=False)) for x in new_types]
    must += l6
    cmd_ids = [r["id"] for r in nm_config.expanded(cfg)["check"]["rules"] if "cmd" in r]  # 这次没执行 cmd 规则:新冻结的 cmd 规则号的 B1 无法核对,不当新违规
    for f in (f for f in res["findings"] if f["state"] == "loosen"):
        skipped = f["rule"] == "B1" and any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(i), f["msg"]) for i in cmd_ids)
        must.append(t("RI_UNEXEC" if skipped else "RI_LOOSEN", f["rule"], f["msg"]))
    out.append(t("RI_LEVEL", rv["level"]) + (" [must-review]" if must else ""))  # 第一行就能判定要不要审(审查 skill 只留这一行)
    live = [f for f in res["findings"] if f["state"] in ("new", "worse", "grew")]
    live.sort(key=lambda f: (f["level"] != "red", f["rule"], f["file"], f["line"]))
    for title, lines in ((t("RI_MUST"), must),
                         (t("RI_FINDINGS"), ["%s %s %s%s %s" % (nm_name("level", f["level"]), f["rule"], f["file"], ":%d" % f["line"] if f["line"] else "", f["msg"]) for f in live]),
                         (t("RI_LESSONS"), ["%s [%s]" % (e["title"], e["file"]) for e in entries if e["paths"] and nm_rules.why_not(e) != "glob" and _hits(e["paths"], diff)])):
        if lines:
            out += ["\n## " + title, "\n".join(lines)]
    p = subprocess.run(["git", "diff", a.base, "HEAD"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise ValueError("git diff: " + p.stderr.strip())
    out += ["\n## " + t("RI_DIFF"), p.stdout.rstrip("\n")]
    if a.fragment:
        with open(a.fragment, encoding="utf-8-sig") as f:
            out += ["\n## " + t("RI_FRAGMENT"), f.read().rstrip("\n")]
    text = "\n".join(out)
    if not a.cmd:
        print(text)
        return 0
    checklist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "lean-change", "review-checklist.md")
    with open(checklist, encoding="utf-8") as f:
        prompt = f.read() + "\n\n" + text
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")  # Python 审查器按 UTF-8 收发;非 Python 的自己也必须收发 UTF-8
    try:
        r = subprocess.run(nm_config.expanded(cfg)["review"]["cmd"], input=prompt, capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)
    except subprocess.TimeoutExpired:
        raise ValueError(t("RI_CMD_TIMEOUT"))
    if r.returncode:
        raise ValueError(t("RI_CMD_FAILED", r.returncode, r.stderr))
    print(r.stdout)
    return 0


def _hits(paths, diff):
    matchers = [pathglob.compile(g).match for g in pathglob.split_globs(paths)]
    return any(m(p) for p in diff for m in matchers)


def _externals(snap, d):
    """教训库里的条目 -> {去空白小写的标题: (是否已核实, 是否外部来源, 标题)}。"""
    return {re.sub(r"\s+", "", e["title"]).lower(): (e["verified"], lessons.is_external(e), e["title"])
            for p in snap.ls(d, ".md") for e in lessons.parse_text(snap.text(p), p)}


def _l6(base, bdir, cand, cdir):
    """L6:基准里带外部来源的条目,在待检里被去掉来源行,或状态从非已核实变成已核实。条目整条删掉不算(没有转正)。"""
    old, new = _externals(base, bdir), _externals(cand, cdir)
    out = []
    for k, (was_ok, ext, title) in old.items():
        if ext and k in new:
            ok, still, _ = new[k]
            if not still:
                out.append(t("RI_L6_SRC", title))
            elif ok and not was_ok:
                out.append(t("RI_L6_OK", title))
    return out
