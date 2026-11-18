"""nomess review-input <基准> [片段文件]:审查者的全部输入(零 token,子代理和 review.cmd 用同一份)。基准 = 提交号或分支名。
顺序写死:第一行审查档(diff 涉及文件里按 scopes 最严的一个,点出是哪个文件定的;有必审项时行末加 [must-review])→ 必审(新增 allow、新冻结的规则号、被放宽的基线和配置)→
新增的红黄项(存量不列)→ diff 涉及文件命中的教训标题(教训的 `路径:` 匹配改动文件)→ diff → 片段文件(相关的设计片段,原样)。
检查结果取 check.evaluate(HEAD 的树, 基准的树, exec_cmd=False):不跑项目里的任何代码。"""
import json
import os
import re
import subprocess

import check
import lessons
import nm_config
import pathglob
import rules as nm_rules
import snapshot
from messages import name as nm_name, t


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess review-input", description="everything a reviewer needs for HEAD against a base: review level, must-review items, new findings, related lessons, diff")
    ap.add_argument("base", help="base commit or branch (the trusted side of the diff)")
    ap.add_argument("fragment", nargs="?", help="a file with the relevant design fragment, appended unchanged at the end")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    root = os.path.dirname(config)
    with snapshot.open_snapshot(root, "tree", "HEAD") as cand, snapshot.open_snapshot(root, "tree", a.base) as base:
        res = check.evaluate(cand, base, exec_cmd=False)
        if res["skipped"]:
            print(res["skipped"])
            return 0
        diff = cand.diff(base)
        cfg = nm_config.parse(cand.text(nm_config.CONFIG_NAME), nm_config.CONFIG_NAME)
        entries = lessons.snapshot_entries(cand, nm_config.expanded(cfg)["lessons_dir"])
    if not diff:
        print(t("RI_EMPTY"))
        return 0
    rv = res["review"]
    must = [t("RI_ALLOW", json.dumps(x, ensure_ascii=False)) for x in res["new_allow"]]
    must += [t("RI_FROZEN", r) for r in res["new_frozen"]]
    cmd_ids = [r["id"] for r in nm_config.expanded(cfg)["check"]["rules"] if "cmd" in r]  # 这次没执行 cmd 规则:新冻结的 cmd 规则号的 B1 无法核对,不当新违规
    for f in (f for f in res["findings"] if f["state"] == "loosen"):
        skipped = f["rule"] == "B1" and any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(i), f["msg"]) for i in cmd_ids)
        must.append(t("RI_UNEXEC" if skipped else "RI_LOOSEN", f["rule"], f["msg"]))
    print(t("RI_LEVEL", rv["level"], rv["file"]) + (" [must-review]" if must else ""))  # 第一行就能判定要不要审(审查 skill 只留这一行)
    live = [f for f in res["findings"] if f["state"] in ("new", "worse", "grew")]
    live.sort(key=lambda f: (f["level"] != "red", f["rule"], f["file"], f["line"]))
    for title, lines in ((t("RI_MUST"), must),
                         (t("RI_FINDINGS"), ["%s %s %s%s %s" % (nm_name("level", f["level"]), f["rule"], f["file"], ":%d" % f["line"] if f["line"] else "", f["msg"]) for f in live]),
                         (t("RI_LESSONS"), ["%s [%s]" % (e["title"], e["file"]) for e in entries if e["paths"] and nm_rules.why_not(e) != "glob" and _hits(e["paths"], diff)])):
        if lines:
            print("\n## " + title)
            print("\n".join(lines))
    p = subprocess.run(["git", "diff", a.base, "HEAD"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise ValueError("git diff: " + p.stderr.strip())
    print("\n## " + t("RI_DIFF"))
    print(p.stdout.rstrip("\n"))
    if a.fragment:
        with open(a.fragment, encoding="utf-8-sig") as f:
            print("\n## " + t("RI_FRAGMENT"))
            print(f.read().rstrip("\n"))
    return 0


def _hits(paths, diff):
    matchers = [pathglob.compile(g).match for g in pathglob.split_globs(paths)]
    return any(m(p) for p in diff for m in matchers)
