"""测试共用的小工具:跑 nomess 子命令、造临时仓库、记失败项。tests/run.py 和各 tests/test_*.py 都从这里 import(import 它不会跑任何测试)。
--timing(命令行参数)时另查每条 nomess 命令不超过 2 秒。"""
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.normpath(os.path.join(HERE, ".."))
NOMESS = os.path.join(PLUGIN, "scripts", "nomess.py")
fails = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


TIMING = "--timing" in sys.argv


def nm(cwd, *args, env=None):
    t = time.perf_counter()
    p = subprocess.run([sys.executable, NOMESS, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, **env) if env else None, timeout=120)
    dt = time.perf_counter() - t
    print("$ nomess %s  -> %d, %.2fs" % (" ".join(args), p.returncode, dt))
    if p.stdout.strip():
        print("   " + p.stdout.strip().replace("\n", "\n   ")[:600])
    if p.stderr.strip():
        print("   [err] " + p.stderr.strip()[:300])
    if TIMING and dt >= 2:
        fails.append("超过 2 秒: %s" % " ".join(args))
    return p


def expect(cond, what):
    if not cond:
        fails.append(what)
        print("   FAIL: " + what)


def digest(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def put(root, rel, text, mode="w"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if isinstance(text, bytes):
        open(p, "wb").write(text)
    else:
        with open(p, mode, encoding="utf-8", newline="\n") as f:
            f.write(text)
    return p


def mkrepo(tmp, name, cfg, files=()):
    root = os.path.join(tmp, name)
    os.makedirs(root)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    cfg = dict({"format": "nomess/1", "main_branch": "main", "lang": "zh-CN", "size": "medium"}, **cfg)
    put(root, "nomess.json", json.dumps(cfg, ensure_ascii=False))
    put(root, ".gitignore", ".nomess/\n")
    for rel, text in files:
        put(root, rel, text)
    return root


def read(root, rel):
    return open(os.path.join(root, rel), encoding="utf-8").read()
