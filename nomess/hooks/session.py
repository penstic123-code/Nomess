"""SessionStart 钩子:零 token,没事什么都不输出;有事只往标准输出打一行英文(SessionStart 的标准输出会进模型上下文)。
判断顺序(先中先停):不在 git 仓库 / 环境变量 CI 有值 / git config nomess.auto 为 false / userConfig.auto_init 关 -> 不输出;
没有 nomess.json -> 启用提示;上次整理的总结还没告诉用户 -> 让模型转告;dream.due() 为真 -> 让模型后台调 dream skill。
auto_init 的读法:官方文档(code.claude.com/docs/en/plugins-reference,User configuration)写明每个 userConfig 选项以
CLAUDE_PLUGIN_OPTION_<KEY 大写> 导出给钩子进程,所以读 CLAUDE_PLUGIN_OPTION_AUTO_INIT;没设就是缺省(开)。
动手的是模型:钩子不能直接调 skill,只说一行。stdin 按 UTF-8 字节读(Windows 缺省 GBK 会让中文路径乱码)。"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
OFF_VALUES = ("false", "0", "no", "off")

ENABLE = ('nomess is not enabled in this repo. Before you first change any file, run `"{py}" "{nomess}" init --auto --lang <en|zh-CN: the language the user writes in>`, '
          'then tell the user in one sentence that nomess is enabled (to undo: `"{py}" "{nomess}" off`). Questions and read-only work do not count.')
DREAM = "Invoke the nomess:dream skill with argument `auto`; don't wait for it; when it returns, relay its one-line summary to the user."


def _git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip() if p.returncode == 0 else None


def decide(cwd, env):
    """要给模型的那一行,没事返回 None。"""
    root = _git(cwd, "rev-parse", "--show-toplevel")
    if not root or env.get("CI") or _git(root, "config", "nomess.auto") == "false":
        return None
    if env.get("CLAUDE_PLUGIN_OPTION_AUTO_INIT", "").strip().lower() in OFF_VALUES:
        return None
    if not os.path.isfile(os.path.join(root, "nomess.json")):
        return ENABLE.format(py=sys.executable, nomess=os.path.join(SCRIPTS, "nomess.py"))
    sys.path.insert(0, SCRIPTS)
    import dream
    summary = dream.take_summary(root)
    if summary:
        return "Tell the user: " + summary
    return DREAM if dream.due(root) else None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        data = {}
    line = decide(data.get("cwd") or os.getcwd(), os.environ)
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
