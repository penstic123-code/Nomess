"""nomess doctor [--python 名字]:零 token 的自检,每项一行,坏的带一句修法。
查:Claude Code 版本、运行这个脚本的 Python 版本、钩子用的解释器(从 ~/.claude/settings.json 的 pluginConfigs 读,或 --python 指定)、
git、nomess.json 能不能读、提交前钩子能不能跑、CLAUDE.md 有没有导入 AGENTS.md、git 钩子接入(按接入方式、逐 worktree)、.nomess/cache/ 大小。有失败项退出码 1。"""
import json
import os
import re
import shutil
import subprocess
import sys

import doccheck
import githook
import nm_config
import snapshot
from messages import t

MIN_CLAUDE = "2.1.277"  # 直接执行的 hook、userConfig 的 options(2.1.271)、直接读 AGENTS.md(2.1.277)三者里最高的
PLUGIN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROBE = '{"tool_name": "Bash", "tool_input": {"command": "echo nomess-doctor"}, "cwd": "."}'  # 不是 git 命令:钩子应零输出退出 0
VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _ver(s):
    m = VERSION_RE.search(s)
    return tuple(int(x) for x in m.groups()) if m else None


def _run(cmd, stdin=None):
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)


def configured_python():
    """用户在启用插件时选的解释器名(~/.claude/settings.json 的 pluginConfigs.<nomess@市场>.options.python);没选返回 None。"""
    p = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            cfgs = json.load(f).get("pluginConfigs", {})
    except (OSError, ValueError):
        return None
    for key, v in cfgs.items():
        if key.split("@")[0] == "nomess":
            return v.get("options", {}).get("python")
    return None


def probe_python(name):
    """(Python 版本字符串 | None):解释器名能不能真跑(Windows 没装 Python 时 python3 是应用商店占位程序)。"""
    if not shutil.which(name):
        return None
    try:
        p = _run([name, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 and _ver(p.stdout) else None


def checks(start, python_name):
    """[(状态 ok|warn|fail, 文字)]。"""
    out = []
    # Claude Code
    try:
        v = _ver(_run(["claude", "--version"]).stdout)
    except (OSError, subprocess.TimeoutExpired):
        v = None
    if v is None:
        out.append(("warn", t("DR_CLAUDE_NONE", MIN_CLAUDE)))
    elif v < _ver(MIN_CLAUDE):
        out.append(("fail", t("DR_CLAUDE_OLD", "%d.%d.%d" % v, MIN_CLAUDE)))
    else:
        out.append(("ok", t("DR_CLAUDE_OK", "%d.%d.%d" % v, MIN_CLAUDE)))
    # 运行 doctor 的 Python(nomess.py 入口已拦掉 3.9 以下,这里是万一别的入口)
    cur = "%d.%d.%d" % sys.version_info[:3]
    out.append(("ok", t("DR_PY_OK", cur)) if sys.version_info >= (3, 9) else ("fail", t("DR_PY_OLD", cur)))
    # 钩子用的解释器
    name = python_name or configured_python()
    hook_py = sys.executable
    if name is None:
        out.append(("warn", t("DR_HOOKPY_UNSET")))
    else:
        pv = probe_python(name)
        if pv is None or _ver(pv) < (3, 9):
            out.append(("fail", t("DR_HOOKPY_MISSING", name)))
        else:
            out.append(("ok", t("DR_HOOKPY_OK", name, pv)))
            hook_py = name
    # git
    try:
        g = _run(["git", "--version"])
        out.append(("ok", t("DR_GIT_OK", g.stdout.strip())) if g.returncode == 0 else ("fail", t("DR_GIT_NONE")))
    except (OSError, subprocess.TimeoutExpired):
        out.append(("fail", t("DR_GIT_NONE")))
    # nomess.json
    base = os.path.abspath(start)
    try:
        config = nm_config.find_config(start)
        nm_config.load(config)
        base = os.path.dirname(config)
        out.append(("ok", t("DR_CFG_OK", config.replace("\\", "/"))))
    except FileNotFoundError:
        out.append(("fail", t("DR_CFG_NONE", base.replace("\\", "/"))))
    except (ValueError, OSError) as e:
        out.append(("fail", t("DR_CFG_BAD", e)))
    # 提交前钩子能不能跑
    try:
        p = _run([hook_py, os.path.join(PLUGIN, "hooks", "guard.py")], stdin=PROBE)
        bad = None if p.returncode == 0 and not p.stdout.strip() else (p.stderr.strip() or p.stdout.strip() or "exit %d" % p.returncode)[-200:]
    except (OSError, subprocess.TimeoutExpired) as e:
        bad = str(e)
    out.append(("ok", t("DR_HOOK_OK")) if bad is None else ("fail", t("DR_HOOK_BAD", hook_py.replace("\\", "/"), bad.replace("\n", " "))))
    # CLAUDE.md 有没有导入 AGENTS.md
    has_a, has_c = (os.path.isfile(os.path.join(base, n)) for n in ("AGENTS.md", "CLAUDE.md"))
    if not has_a:
        out.append(("ok", t("DR_IMPORT_NA")))
    elif not has_c:
        out.append(("ok", t("DR_IMPORT_ALONE")))
    else:
        with snapshot.open_snapshot(base, "worktree") as snap:
            out.append(("fail", t("DR_IMPORT_BAD")) if any(f["rule"] == "AGENTS2" for f in doccheck.agents(snap))
                       else ("ok", t("DR_IMPORT_OK")))
    # git 钩子接入:按接入方式查(原生 / husky / pre-commit 框架);hooksPath 是相对路径时每个 worktree 各自解析,逐个查
    try:
        top = snapshot.toplevel(base)
        sts = [(top, githook.status(top))]
        if githook.relative_hooks_path(top):
            sts += [(w, githook.status(w)) for w in githook.worktrees(top) if os.path.normcase(os.path.normpath(w)) != os.path.normcase(os.path.normpath(top))]
        if sts[0][1]["stub"]:
            out.append(("warn", t("DR_GITHOOK_OFF")))
        else:
            for w, st in sts:
                bad = [h for h, v in st["hooks"].items() if v != "wired"]
                where = (st["manager"], str(st["hook_dir"]).replace("\\", "/"), st["launcher"].replace("\\", "/"))
                if bad or not st["launcher_ok"]:
                    out.append(("warn", t("DR_GITHOOK_BAD", ", ".join(bad) or "launcher", w.replace("\\", "/"), *where)))
                elif w == top:
                    out.append(("ok", t("DR_GITHOOK_OK", *where)))
    except snapshot.SnapshotError:
        pass
    # 缓存大小(.nomess/cache/ 可随时删,下次检查自动重建)
    n, size = 0, 0
    for r, _, fs in os.walk(os.path.join(base, ".nomess", "cache")):
        n += len(fs)
        size += sum(os.path.getsize(os.path.join(r, f)) for f in fs)
    out.append(("ok", t("DR_CACHE", n, "%.1f KB" % (size / 1024))))
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess doctor", description="self-check, one line per item, with a fix for each problem")
    ap.add_argument("--python", metavar="NAME", help="hook interpreter name to check (default: read from ~/.claude/settings.json)")
    a = ap.parse_args(argv)
    try:  # 先设好提示语的语言;读不到配置就用缺省
        nm_config.load(nm_config.find_config())
    except (FileNotFoundError, ValueError, OSError):
        pass
    res = checks(os.getcwd(), a.python)
    for state, text in res:
        print("%s  %s" % ({"ok": t("DR_OK"), "warn": t("DR_WARN"), "fail": t("DR_FAIL")}[state], text))
    bad = sum(s == "fail" for s, _ in res)
    if bad:
        print(t("DR_SUMMARY", bad))
    return 1 if bad else 0
