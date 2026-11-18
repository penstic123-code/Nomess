#!/usr/bin/env python
"""nomess 入口:只做子命令分发。  check | docgen | map | rules | lessons | status | doctor | review-input | refresh | hooks | git-hook。退出码:0 通过,1 有新红项/过时,2 运行故障(配置不对、超时、生成器失败、Python 版本不够)"""
import os
import re
import subprocess
import sys

if sys.version_info < (3, 9):  # 先于其他导入:后面的模块用了 3.9 的写法
    print("nomess: Python 3.9+ required")
    sys.exit(2)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from messages import t

COMMANDS = ("check", "docgen", "map", "rules", "lessons", "status", "doctor", "review-input", "refresh", "hooks", "git-hook")
GITHOOK = ("refresh", "hooks", "git-hook")  # 这三个在 githook.py,入口名是 main_<命令>


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # Windows 缺省 GBK 和 CRLF;输出要和 Mac / Linux 逐字节相同
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(t("USAGE", " | ".join(COMMANDS)))
        return 2
    cmd = sys.argv[1]
    mod, fn = ("githook", "main_" + cmd.replace("-", "_")) if cmd in GITHOOK else (cmd.replace("-", "_"), "main")
    import snapshot
    try:
        return getattr(__import__(mod), fn)(sys.argv[2:])
    except (ValueError, KeyError, OSError, re.error, snapshot.SnapshotError) as e:  # 配置不对、正则非法、文件/进程访问失败
        print("nomess: %s" % e, file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as e:
        print("nomess: " + t("TIMEOUT", e.timeout, e.cmd), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
