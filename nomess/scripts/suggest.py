"""第 4 层:升降档建议(零 token,只用 git 历史和树)。`nomess status` 够线给一行,`status --suggest` 列全部信号;只建议相邻一级,不改 nomess.json。
信号(窗口和线都在 nomess.json 的 suggest 段,`"suggest": false` 全关):
  parallel  窗口内合进主分支(第一父链)的合并提交数,每个合并提交带进一个分支           升
  overlap   窗口内合并提交两边(对 merge-base)都改过的文件数                             升
  inbox     inbox 条数 >= lessons_remind,且最老条目的更新日期早于 inbox_stale_days 天    升
  systems   子系统数(map.systems_of:没填按源文件顶层目录):小->中 systems_medium,中->大 systems_large   升
  single    down_window_days 内作者邮箱只有一个、整个窗口内仓库已存在,且 parallel、overlap 都是 0   降
大项目没有更高一级,只出降档。建议只在 status 和状态栏出,不进 AGENTS.md。
status 文本模式提示过的建议记进 .nomess/suggest.json(键 `当前级->建议级`),size 没变就不再提示,size 变了清空;--json 和 --suggest 不记录、不受限。"""
import datetime
import json
import os
import subprocess
import time

import deps
import lessons
import map as nm_map
import nm_config
import snapshot
from messages import t

RECORD = os.path.join(".nomess", "suggest.json")
DAY = 86400


def _git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip() if p.returncode == 0 else ""


def _merges(root, rev, since, now):
    """窗口内第一父链上的合并提交:[(第一父, 第二父)]。"""
    out = []
    for line in _git(root, "log", "--first-parent", "--merges", "--since=%d" % since, "--format=%P %ct", rev).splitlines():
        *parents, ts = line.split()
        if len(parents) >= 2 and since <= int(ts) <= now:
            out.append((parents[0], parents[1]))
    return out


def _overlap(root, merges):
    files = set()
    for a, b in merges:
        base = _git(root, "merge-base", a, b)
        if base:
            sides = [set(_git(root, "diff", "--name-only", base, x).splitlines()) for x in (a, b)]
            files |= sides[0] & sides[1]
    return len(files)


def evaluate(root, rev, now, sug):
    """{size, target(建议的级或 None), signals: {名: 数}, reasons: [文字]}。sug 是展开后的 suggest 段。rev 没有提交或没有 nomess.json 返回 None。"""
    if not snapshot.has_commit(root, rev):
        return None
    with snapshot.open_snapshot(root, "tree", rev) as snap:
        text = snap.text(nm_config.CONFIG_NAME)
        if text is None:
            return None
        cfg = json.loads(text.lstrip("﻿"))
        size = cfg.get("size", nm_config.DEFAULTS["size"])
        win = sug["window_days"]
        merges = _merges(root, rev, now - win * DAY, now)
        sig = {"parallel": len(merges), "overlap": _overlap(root, merges), "systems": len(nm_map.systems_of(cfg, deps.all_files(snap))[0])}
        inbox = os.path.join(cfg.get("lessons_dir", "docs/lessons"), lessons.INBOX).replace("\\", "/")
        itext = snap.text(inbox)
        es = lessons.parse_text(itext, lessons.INBOX) if itext else []
        dates = [e["updated"] for e in es if e["updated"]]
        cut = datetime.date.fromtimestamp(now - sug["inbox_stale_days"] * DAY).isoformat()
        sig["inbox"], sig["remind"] = len(es), cfg.get("lessons_remind", nm_config.DEFAULTS["lessons_remind"])
        sig["inbox_old"] = bool(dates) and min(dates) < cut
    down_cut = now - sug["down_window_days"] * DAY
    authors = set(_git(root, "log", rev, "--since=%d" % down_cut, "--format=%ae").splitlines())
    roots = [int(x) for x in _git(root, "log", rev, "--max-parents=0", "--format=%ct").split()]
    sig["single"] = len(authors) == 1 and bool(roots) and min(roots) <= down_cut and not sig["parallel"] and not sig["overlap"]
    i = nm_config.SIZES.index(size)
    ups = []
    if sig["parallel"] >= sug["parallel_branches"]:
        ups.append(t("SUG_PARALLEL", win, sig["parallel"]))
    if sig["overlap"] >= sug["overlap_files"]:
        ups.append(t("SUG_OVERLAP", win, sig["overlap"]))
    if sig["inbox"] >= sig["remind"] and sig["inbox_old"]:
        ups.append(t("SUG_INBOX", sig["inbox"], sug["inbox_stale_days"]))
    line = {"small": sug["systems_medium"], "medium": sug["systems_large"]}.get(size)
    if line is not None and sig["systems"] >= line:
        ups.append(t("SUG_SYSTEMS", sig["systems"]))
    res = {"size": size, "target": None, "signals": sig, "reasons": []}
    if ups and i < len(nm_config.SIZES) - 1:
        res.update(target=nm_config.SIZES[i + 1], reasons=ups)
    elif sig["single"] and i > 0:
        res.update(target=nm_config.SIZES[i - 1], reasons=[t("SUG_SINGLE", sug["down_window_days"])])
    return res


def line(res):
    return t("SUG_LINE", res["target"], "; ".join(res["reasons"]))


def current(root, cfg, now=None):
    """现在 HEAD 上的建议(没有返回 None)。cfg 是 nm_config.expanded 的结果。"""
    sug = cfg["suggest"]
    res = sug and evaluate(root, "HEAD", now or int(time.time()), sug)
    return res if res and res["target"] else None


def fresh(root, res, record=True):
    """status 里这条建议要不要提示:没提示过(记录里没有,或 size 变了)才提示,record 为真时记下来。返回文字或 ""。"""
    path = os.path.join(root, RECORD)
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        rec = {}
    if rec.get("size") != res["size"]:
        rec = {"size": res["size"], "shown": {}}
    key = "%s->%s" % (res["size"], res["target"])
    if key in rec["shown"]:
        return ""
    if record:
        rec["shown"][key] = datetime.date.today().isoformat()
        nm_config.atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return line(res)


def listing(root, cfg):
    """status --suggest:全部信号和数,不受提示记录限制。"""
    sug = cfg["suggest"]
    if not sug:
        return [t("SUG_OFF")]
    res = evaluate(root, "HEAD", int(time.time()), sug)
    if res is None:
        return [t("SUG_NONE")]
    s = res["signals"]
    worktrees = sum(1 for l in _git(root, "worktree", "list").splitlines() if l.strip())
    out = [t("SUG_SIZE", res["size"]),
           t("SUG_ROW", "parallel", "%d (>= %d), worktrees %d" % (s["parallel"], sug["parallel_branches"], worktrees)),
           t("SUG_ROW", "overlap", "%d (>= %d)" % (s["overlap"], sug["overlap_files"])),
           t("SUG_ROW", "inbox", "%d (>= %d and oldest older than %d days: %s)" % (s["inbox"], s["remind"], sug["inbox_stale_days"], s["inbox_old"])),
           t("SUG_ROW", "systems", "%d (small->medium >= %d, medium->large >= %d)" % (s["systems"], sug["systems_medium"], sug["systems_large"])),
           t("SUG_ROW", "single", "%s (one author in %d days, no parallel, no overlap)" % (s["single"], sug["down_window_days"]))]
    out.append(line(res) if res["target"] else t("SUG_NO_ADVICE"))
    return out
