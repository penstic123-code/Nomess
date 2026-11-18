"""PreToolUse 钩子:只挡代理绕过提交闸门(闸门本身是 git 钩子,见 scripts/githook.py)。误伤的代价只是代理换个写法。
命令先按 shell 规则切词(引号、转义),按 && ; || | & 换行分段;每段认出 git / git.exe(可带路径)的一次调用,
PowerShell 段首的 & 是调用运算符、不是分段符;跟踪段首 cd <目录> 和 git -C <目录>,按这次调用的目标目录找仓库和 nomess.json。
挡:commit / merge 的 --no-verify、commit 短选项簇里的 n(-n、-nm"x",在第一个带值字母之前)、-c core.hooksPath=…、git config 设置 core.hooksPath(只读查询放行)。merge 带 --no-commit / --squash 不要求 pre-merge-commit 接线。
选项值(-m / -F / --message 等)和 -- 之后的参数不看。
顺手查接入(按阶段,接入方式见 githook.status:原生、husky、pre-commit 框架):commit 要 pre-commit 接上,merge 要 pre-merge-commit 接上,没接上就挡;
启动器里的插件路径不是当前插件 -> 重写启动器;从没装过 -> 提示一行,不替用户装;启动器是 uninstall 留下的存根(主动停用)-> 不查。目标仓库没有 nomess.json 的调用直接放行。
输出纯 ASCII 的 JSON,退出码恒为 0(不同 shell 对原生命令退出码和 stderr 的转手不一致)。stdin 是 hook 输入 JSON。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

SEPS = {"&&", "||", ";", "|", "&", "\n", ";;", "|&"}
READS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--unset", "--unset-all"}  # git config 的只读 / 删除动作
STAGE = {"commit": "pre-commit", "merge": "pre-merge-commit"}
# 带值的选项。SHORT_VAL:值在同一个词的剩余部分,没有就是下一个词;SHORT_ATTACHED:可选值,只能贴在同一个词里
SHORT_VAL = {"commit": "mFCct", "merge": "mFsX"}
SHORT_ATTACHED = {"commit": "uS", "merge": "S"}
LONG_VAL = {"commit": {"--message", "--file", "--reuse-message", "--reedit-message", "--fixup", "--squash", "--author", "--date",
                       "--cleanup", "--template", "--trailer", "--pathspec-from-file"},
            "merge": {"--message", "--file", "--strategy", "--strategy-option", "--cleanup", "--into-name"}}


def emit(obj):
    print(json.dumps(obj))  # 缺省 ensure_ascii=True


def deny(reason):
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}})


def words(command, tool):
    """shell 切词:[(文本, 是否来自引号)]。引号(单、双)和反斜杠按 POSIX 规则;PowerShell 里反斜杠是路径分隔符,不当转义。
    不在引号里的连续 & ; | 是一个分隔符词(引号里的就是普通文本),换行也是;不处理 # 注释(ticket#123 是普通字符)。引号没配上就吃到结尾。"""
    ps = tool == "PowerShell"
    out, cur, quoted = [], None, False  # cur: 正在拼的词(None = 没有)
    i, n = 0, len(command)

    def flush():
        nonlocal cur, quoted
        if cur is not None:
            out.append((cur, quoted))
        cur, quoted = None, False

    while i < n:
        c = command[i]
        if c in " \t\r":
            flush()
        elif c == "\n":
            flush()
            out.append(("\n", False))
        elif c in "&;|":
            flush()
            j = i
            while j < n and command[j] in "&;|":
                j += 1
            out.append((command[i:j], False))
            i = j - 1
        elif c == "'":
            j = command.find("'", i + 1)
            j = n if j < 0 else j
            cur, quoted = (cur or "") + command[i + 1:j], True
            i = j
        elif c == '"':
            buf, j = "", i + 1
            while j < n and command[j] != '"':
                if not ps and command[j] == "\\" and j + 1 < n and command[j + 1] in '"\\$`':  # POSIX 双引号里反斜杠只转义这四个
                    j += 1
                buf += command[j]
                j += 1
            cur, quoted = (cur or "") + buf, True
            i = j
        elif c == "\\" and not ps and i + 1 < n:
            cur = (cur or "") + command[i + 1]
            i += 1
        else:
            cur = (cur or "") + c
        i += 1
    flush()
    return out


def _opts_bypass(sub, args):
    """commit / merge 参数里的绕过写法,没有返回 None。"""
    skip = False
    for a in args:
        if skip:
            skip = False
        elif a == "--":
            break
        elif a.startswith("--"):
            name = a.split("=", 1)[0]
            if len(name) >= len("--no-veri") and "--no-verify".startswith(name):  # git 认唯一前缀
                return "--no-verify"
            skip = name in LONG_VAL[sub] and "=" not in a
        elif a.startswith("-") and len(a) > 1:
            for i, ch in enumerate(a[1:]):
                if ch == "n" and sub == "commit":
                    return "-n"
                if ch in SHORT_ATTACHED[sub]:
                    break
                if ch in SHORT_VAL[sub]:
                    skip = i == len(a) - 2  # 值不在同一个词里,就是下一个词
                    break
    return None


def _sets_hooks_path(args):
    """git config 的参数是在设置 core.hooksPath:键后面跟了值,或带 --add / --replace-all。--get / --list / --unset / 只给键名都不算。"""
    pos = [a for a in args if not a.startswith("-")]
    keys = [i for i, a in enumerate(pos) if a.lower() == "core.hookspath"]
    if not keys:
        return False
    if {"--add", "--replace-all"} & set(args):
        return True
    return len(pos) > keys[0] + 1 and not READS & set(args)


def calls(command, cwd, tool="Bash"):
    """命令里每次 git 调用:[(目标目录, 子命令, 绕过写法或 None)]。纯函数,不碰磁盘和 git。"""
    out, seg = [], []
    for w, quoted in words(command, tool) + [("\n", False)]:
        if quoted or w != "\n" and set(w) - set("&;|"):  # 引号里的或普通词
            seg.append(w)
            continue
        if tool == "PowerShell" and w == "&" and not seg:  # 段首的 & 是调用运算符,后面跟命令
            continue
        while seg and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[0]):  # 前置的 VAR=值
            seg = seg[1:]
        if len(seg) >= 2 and seg[0] in ("cd", "pushd", "Set-Location"):
            cwd = os.path.join(cwd, seg[1])  # 影响后面的段
        elif seg and re.sub(r"\.exe$", "", re.split(r"[\\/]", seg[0])[-1].lower()) == "git":
            d, i, hooks_path = cwd, 1, False
            while i < len(seg) and seg[i].startswith("-"):
                if seg[i] in ("-C", "-c") and i + 1 < len(seg):
                    if seg[i] == "-C":
                        d = os.path.join(d, seg[i + 1])
                    else:
                        hooks_path |= seg[i + 1].split("=", 1)[0].lower() == "core.hookspath"
                    i += 2
                else:
                    i += 1
            sub, args = (seg[i], seg[i + 1:]) if i < len(seg) else ("", [])
            if hooks_path or (sub == "config" and _sets_hooks_path(args)):
                why = "core.hooksPath"
            else:
                why = _opts_bypass(sub, args) if sub in STAGE else None
            if sub == "merge" and {"--no-commit", "--squash"} & set(args):
                sub = ""  # 这次合并不创建提交,不跑 pre-merge-commit,不要求它接线
            out.append((d, sub, why))
        seg = []
    return out


def main():
    for s in (sys.stdin, sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")  # Windows 缺省是 GBK,hook 协议要 UTF-8
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if "git" not in command:
        return 0
    import githook
    import nm_config
    import snapshot
    from messages import t
    never = None
    for d, sub, why in calls(command, data.get("cwd") or os.getcwd(), data.get("tool_name")):
        if not why and sub not in STAGE:
            continue
        try:
            config = nm_config.find_config(d)
        except FileNotFoundError:
            continue
        try:
            nm_config.load(config)  # 按项目语言出提示;配置不合法由 git 钩子报
        except ValueError:
            pass
        if why:
            return deny(t("GUARD_BYPASS", why)) or 0
        try:
            root = snapshot.toplevel(os.path.dirname(config))
        except snapshot.SnapshotError:
            continue
        st = githook.status(root)
        if st["stub"]:  # nomess hooks uninstall 留下的存根:主动停用,不催装也不拦
            continue
        if not st["launcher_ok"]:
            never = t("GUARD_NEVER")
        elif st["hooks"][STAGE[sub]] != "wired":
            return deny(t("GUARD_UNWIRED", STAGE[sub])) or 0
        elif not st["current"]:
            githook.write_launcher(root)  # 升级后插件路径变了:重写这一个自己的文件
    if never:
        emit({"systemMessage": never})
    return 0


if __name__ == "__main__":
    sys.exit(main())
