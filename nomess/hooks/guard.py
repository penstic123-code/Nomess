"""PreToolUse 钩子:只挡代理绕过提交闸门(闸门本身是 git 钩子,见 scripts/githook.py)。误伤的代价只是代理换个写法。
命令先按 shell 规则切词(引号、转义),按 && ; || | & 换行分段;每段认出 git / git.exe(可带路径)的一次调用,
PowerShell 段首的 & 是调用运算符、不是分段符;跟踪段首 cd <目录> 和 git -C <目录>,按这次调用的目标目录找仓库和 nomess.json。
挡:commit / merge 的 --no-verify、commit 短选项簇里的 n(-n、-nm"x",在第一个带值字母之前)、-c core.hooksPath=…、git config 设置 core.hooksPath(只读查询放行)。merge 带 --no-commit / --squash 不要求 pre-merge-commit 接线。
选项值(-m / -F / --message 等)和 -- 之后的参数不看。
另外挡 Write 新建 docs_root 下不在任何文档类型位置的 .md(stray_doc,规则在 doctypes.blocked)。
顺手查接入(按阶段,接入方式见 githook.status:原生、husky、pre-commit 框架):commit 要 pre-commit 接上,merge 要 pre-merge-commit 接上,没接上就挡;
启动器里的插件路径不是当前插件 -> 重写启动器;从没装过 -> 提示一行,不替用户装;启动器是 uninstall 留下的存根(主动停用)-> 不查。目标仓库没有 nomess.json 的调用直接放行。
另外对三类调用回 permissionDecision=allow(免弹窗,其余一律不表态):① Bash/PowerShell 的命令就是本插件的 nomess.py(解释器 + 脚本绝对路径,或 bin/nomess;
不许管道、串接、重定向、命令替换;子命令只放行白名单 WHITELIST,`off`、`hooks`、`check --freeze`、`refresh` 等照常走权限);
② Edit/Write 的目标是整理 worktree(dream.wt_path)里 dream.writable 认可的文件(文档根和教训目录下的 .md、已有的开发者文档、AGENTS.md、.nomess/dream-notes.md;对外文档不放行);③ 目标是项目记忆目录本层或下一层子目录里的 .md 文件且输入的 agent_id 非空(子代理才有;R0 实测)。
stdin 按 UTF-8 字节读(Windows 缺省 GBK,中文用户名路径会乱码)。
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


PLUGIN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NOMESS = (os.path.join(PLUGIN, "scripts", "nomess.py"), os.path.join(PLUGIN, "bin", "nomess"), os.path.join(PLUGIN, "bin", "nomess.cmd"))


def norm(p):
    """路径比较用:分隔符统一,Windows 上大小写不分。"""
    return os.path.normcase(os.path.normpath(p))


def inside(path, d):
    path, d = norm(os.path.realpath(path)), norm(os.path.realpath(d))  # 先还原成完整路径:Windows 短路径名(RUNNER~1)和长路径要算同一个
    return path == d or path.startswith(d.rstrip(os.sep) + os.sep)


SAFE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./\\:=,")  # 未加引号的词只许这些字符,外加非 ASCII 字母(路径里有中文用户名)
INTERPRETERS = {"python", "python3", "py"}


def _safe_word(w):
    return all(c in SAFE_CHARS or (ord(c) > 127 and c.isalpha()) for c in w)


def _whitelisted(args):
    """nomess.py 后面的参数是不是白名单里的调用:dream begin|land|abort|git-log <词>|mv <a> <b>|rm <a>、init --auto [--lang X] [--size X]、
    lessons find|add|status、status、check(不带 --freeze,含它的缩写)、doctor。"""
    if not args:
        return False
    sub, rest = args[0], args[1:]
    if sub == "dream":
        return rest[:1] in (["begin"], ["land"], ["abort"]) and len(rest) == 1 or rest[:1] == ["git-log"] and len(rest) == 2 or rest[:1] == ["mv"] and len(rest) == 3 or rest[:1] == ["rm"] and len(rest) == 2
    if sub == "init":
        opts, i = set(), 0
        while i < len(rest):
            name, eq, _ = rest[i].partition("=")
            if name == "--auto" and not eq:
                i += 1
            elif name in ("--lang", "--size") and name not in opts:
                i += 1 if eq else 2
            else:
                return False
            opts.add(name)
        return "--auto" in opts and i == len(rest)
    if sub == "lessons":
        return rest[:1] in (["find"], ["add"], ["status"])
    if sub == "check":
        return not any(len(a.split("=")[0]) >= 3 and "--freeze".startswith(a.split("=")[0]) for a in rest)
    return sub in ("status", "doctor")


def is_nomess_command(command, tool):
    """命令就是本插件的 nomess.py(或 bin/nomess)的白名单调用:一段、没有分隔符、没有重定向和命令替换。
    未加引号的词只许 SAFE_CHARS;任何词都不许含 $ 和反引号;PowerShell 另外明确拒 ( ) @ { }。
    解释器只认不带路径的 python / python3 / py(可带 .exe),或与 sys.executable 规范化后完全相同的路径。"""
    if "`" in command or any(ord(c) < 32 or ord(c) == 127 for c in command.rstrip("\n")):  # PowerShell 把单独的 \r 当换行,能串第二条命令
        return False
    ws = words(command, tool)
    if tool == "PowerShell" and ws[:1] == [("&", False)]:  # 段首的 & 是调用运算符
        ws = ws[1:]
    bad = set("$`") | (set("(){}@") if tool == "PowerShell" else set())
    if not ws or any(bad & set(w) or (not q and (set(w) <= set("&;|") or w == "\n" or not _safe_word(w))) for w, q in ws):
        return False
    ws = [w for w, _ in ws]
    first = ws[0]
    if re.sub(r"\.exe$", "", first.lower()) in INTERPRETERS or norm(first) == norm(sys.executable):
        ws = ws[1:]
    return bool(ws) and norm(ws[0]) in {norm(n) for n in NOMESS} and _whitelisted(ws[1:])


def allowed(data):
    """这次调用该不该免弹窗放行。"""
    tool, inp = data.get("tool_name"), data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool in ("Bash", "PowerShell"):
        return is_nomess_command(inp.get("command") or "", tool)
    if tool not in ("Edit", "Write") or not inp.get("file_path"):
        return False
    target = os.path.join(cwd, inp["file_path"])  # 绝对路径时 join 取后者
    import dream
    import snapshot
    try:
        wt = dream.wt_path(cwd)
    except snapshot.SnapshotError:  # 不在 git 仓库里:没有整理 worktree,不放行
        wt = None
    if wt and inside(target, wt):
        return dream.may_edit(cwd, target)
    return bool(data.get("agent_id")) and dream.in_memory(cwd, target)  # 子代理写记忆目录里的 .md(范围见 dream.in_memory)


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


def stray_doc(data):
    """当场挡(13.12 第 1 条):Write 一个还不存在、位于 docs_root 下、不在任何文档类型位置的 .md -> 理由(带最像的位置);否则 None。
    规则在 doctypes.blocked(和 DOC4 新增报红同一条);仓库没有 nomess.json、配置不合法(git 钩子会报)都不管。"""
    inp = data.get("tool_input") or {}
    if data.get("tool_name") != "Write" or not inp.get("file_path"):
        return None
    target = os.path.abspath(os.path.join(data.get("cwd") or os.getcwd(), inp["file_path"]))
    if os.path.exists(target):
        return None
    import doctypes
    import nm_config
    import snapshot
    try:
        config = nm_config.find_config(os.path.dirname(target))
        exp = nm_config.expanded(nm_config.load(config))
    except (FileNotFoundError, ValueError):
        return None
    rel = os.path.relpath(target, os.path.dirname(config)).replace("\\", "/")
    with snapshot.open_snapshot(os.path.dirname(config), "worktree") as snap:  # 快照惰性加载:只在 blocked 要认网站源目录时才列文件
        return doctypes.blocked(rel, exp, snap)


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")  # Windows 缺省是 GBK,hook 协议要 UTF-8
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        return 0
    why = stray_doc(data)  # 先挡后放:整理 worktree 里新建放错位置的页也不放行
    if why:
        return deny(why) or 0
    if allowed(data):
        return emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "permissionDecisionReason": "nomess"}}) or 0
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
