"""nomess status [--json] [--no-exec] [--suggest]:一行概览(给人和扩展看)——生成段过时数、记忆超预算数、inbox 条数、项目记忆目录;
够线时另起一行升降档建议(见 suggest.py,同一条建议只提示一次;--json 不记录)。--suggest 列全部信号和数,不受提示记录限制。
--no-exec 时生成段过时数不跑 cmd / py 生成器(不执行项目代码;做梦出提案用)。
项目记忆目录按 Claude Code 的规则定位(https://code.claude.com/docs/en/memory#storage-location,2026-11-18 核实):
  settings 的 autoMemoryDirectory(策略 > 项目 local > 项目 > 用户)> CLAUDE_CODE_PROJECT_DIR_NAME(配合 CLAUDE_CONFIG_DIR)
  > <配置目录>/projects/<仓库主目录路径里非字母数字都换成 ->/memory(配置目录 = CLAUDE_CONFIG_DIR 或 ~/.claude;worktree 共用主仓库那份)。
  定不下来(目录不存在、大小写不同的同名目录不止一个)时 memory_dir 为空,memory_problem 写原因;不往上级目录猜。
"""
import json
import os
import re
import subprocess
import sys

import check
import lessons
import suggest
import nm_config
import snapshot
from messages import t

def claude_dir():
    """Claude Code 的配置目录:CLAUDE_CONFIG_DIR,没设就是 ~/.claude。"""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


MANAGED = {"win32": r"C:\Program Files\ClaudeCode", "darwin": "/Library/Application Support/ClaudeCode"}.get(sys.platform, "/etc/claude-code")


def _git(d, *args):
    p = subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip() if p.returncode == 0 else None


def project_root(base):
    """Claude Code 记忆用的项目路径:git 主仓库目录(worktree 也归到它);不在 git 里就是 base。"""
    common = _git(base, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(os.path.normpath(common)) == ".git":
        return os.path.dirname(os.path.normpath(common))
    return os.path.normpath(_git(base, "rev-parse", "--show-toplevel") or base)


def _setting(root, key):
    """(值, 来自哪个文件):按 Claude Code 的优先级找第一个写了 key 的 settings 文件。"""
    for p in (os.path.join(MANAGED, "managed-settings.json"), os.path.join(root, ".claude", "settings.local.json"),
              os.path.join(root, ".claude", "settings.json"), os.path.join(claude_dir(), "settings.json")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8-sig") as f:
                v = json.load(f).get(key)
            if v:
                return v, p
    return None, None


def memory_location(base):
    """{"dir": 项目记忆目录或 "", "source": 怎么定的, "problem": 定不下来的原因或 ""}。"""
    root = project_root(base)
    v, src = _setting(root, "autoMemoryDirectory")
    if v:
        d, source = os.path.expanduser(v), "autoMemoryDirectory (%s)" % src
    elif os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME") and os.environ.get("CLAUDE_CONFIG_DIR"):
        d, source = os.path.join(claude_dir(), "projects", os.environ["CLAUDE_CODE_PROJECT_DIR_NAME"], "memory"), "CLAUDE_CODE_PROJECT_DIR_NAME"
    else:
        projects = os.path.join(claude_dir(), "projects")
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(root))
        have = os.listdir(projects) if os.path.isdir(projects) else []
        hits = [n for n in have if n == slug] or ([n for n in have if n.lower() == slug.lower()] if os.name == "nt" else [])
        source = "projects/<%s>" % root.replace("\\", "/")
        if len(hits) > 1:
            return {"dir": "", "source": source, "problem": "ambiguous: " + ", ".join(sorted(hits))}
        d = os.path.join(projects, hits[0] if hits else slug, "memory")
    d = os.path.normpath(d)
    if not os.path.isdir(d):
        return {"dir": "", "source": source, "problem": "not found: " + d.replace("\\", "/")}
    return {"dir": d.replace("\\", "/"), "source": source, "problem": ""}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess status", description="one-line overview: stale sections, memory over budget, inbox, size advice")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-exec", dest="no_exec", action="store_true", help="count stale sections without running cmd / py generators")
    ap.add_argument("--suggest", action="store_true", help="list every size-advice signal and its number instead of the overview")
    a = ap.parse_args(argv)
    config = nm_config.find_config()
    cfg = nm_config.load(config)
    base = os.path.dirname(config)
    exp = nm_config.expanded(cfg)
    if a.suggest:
        print("\n".join(suggest.listing(base, exp)))
        return 0
    loc = memory_location(base)
    mem = loc["dir"]
    over = [f for f in check.memory_check(mem, cfg) if f["rule"] in ("M2", "M3")] if mem and os.path.isfile(os.path.join(mem, "MEMORY.md")) else []
    lessons_dir = cfg.get("lessons_dir", "docs/lessons")
    inbox = os.path.join(base, lessons_dir, lessons.INBOX)
    with snapshot.open_snapshot(base, "worktree") as snap:
        stale = len(check.stale_sections(snap, cfg, not a.no_exec))
    advice = suggest.current(base, exp)
    s = {"stale": stale, "memory_over": len(over), "inbox": len(lessons.parse(inbox)) if os.path.isfile(inbox) else 0,
         "memory_dir": mem, "memory_source": loc["source"], "memory_problem": loc["problem"], "lessons_dir": lessons_dir,
         "suggest": suggest.fresh(base, advice, record=not a.json) if advice else ""}
    if a.json:
        print(json.dumps(s, ensure_ascii=False))
    else:
        print(t("STATUS_LINE", s["stale"], s["memory_over"], s["inbox"], mem or t("NONE")))
        if s["suggest"]:
            print(s["suggest"])
    return 0
