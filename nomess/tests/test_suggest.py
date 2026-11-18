"""P22:升降档建议(suggest.py、status、入口段)。假仓库里 30 天内 3 个分支并行合入,提交时间固定在最近几天。
测:⑧ status 出一行升档建议,再跑不出、--suggest 仍列,改 size 后记录清空;入口段里没有建议行,两个克隆生成逐字节相同。
全过打印 OK,否则列出失败项并退出码 1。不含计时断言。"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

from helpers import expect, fails, mkrepo, nm, put, read

BASE_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def when(days_ago):
    return (datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def git(root, *a, days_ago=0):
    env = dict(BASE_ENV, GIT_AUTHOR_DATE=when(days_ago), GIT_COMMITTER_DATE=when(days_ago))
    p = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p


def commit_all(root, msg, days_ago):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg, days_ago=days_ago)


def merge_branch(root, name, days_ago):
    git(root, "checkout", "-q", "-b", name)
    put(root, "src/%s.py" % name, "# %s\n" % name)
    commit_all(root, name, days_ago + 0.5)
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "merge " + name, name, days_ago=days_ago)


def mkproject(tmp, name):
    root = mkrepo(tmp, name, {"lang": "en", "size": "small",
                               "docgen": {"entry": {"file": "AGENTS.md", "builtin": "agents-entry"}}},
                  [("AGENTS.md", "# P\n\n<!-- GEN:entry BEGIN -->\n<!-- GEN:entry END -->\n"), ("src/a.py", "# a\n")])
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(root, "config", k, v)
    put(root, ".gitignore", ".nomess/\n")
    commit_all(root, "init", 20)
    return root


def body(root):
    return read(root, "AGENTS.md").split("<!-- GEN:entry BEGIN -->")[1].split("<!-- GEN:entry END -->")[0]


def t_status_and_record(tmp):
    root = mkproject(tmp, "sug1")
    for i, name in enumerate(("f1", "f2", "f3")):
        merge_branch(root, name, 6 - i)
    p = nm(root, "status")
    expect("Suggest size `medium`" in p.stdout and "3 branches merged" in p.stdout and p.stdout.count("Suggest size") == 1, "⑧ status 应出一行升档建议: %r" % p.stdout)
    p = nm(root, "status")
    expect("Suggest size" not in p.stdout, "⑧ 提示过的建议再跑不出: %r" % p.stdout)
    expect(json.loads(nm(root, "status", "--json").stdout)["suggest"] == "", "⑧ --json 里也不再出")
    p = nm(root, "status", "--suggest")
    expect("parallel: 3" in p.stdout and "Suggest size `medium`" in p.stdout, "⑧ --suggest 仍列全部信号和建议: %r" % p.stdout)
    # 改 size 并提交:记录清空(旧级 small->medium 的记录没了,只留新级的)
    cfg = json.loads(read(root, "nomess.json"))
    put(root, "nomess.json", json.dumps(dict(cfg, size="medium")))
    commit_all(root, "size", 1)
    p = nm(root, "status")
    rec = json.load(open(os.path.join(root, ".nomess", "suggest.json"), encoding="utf-8"))
    expect(rec["size"] == "medium" and list(rec["shown"]) == ["medium->large"] and "Suggest size `large`" in p.stdout,
           "⑧ 改 size 后记录清空、按新级重新提示: %r %r" % (rec, p.stdout))


def t_entry_line(tmp):
    root = mkproject(tmp, "sug2")
    merge_branch(root, "f1", 5)
    merge_branch(root, "f2", 4)  # parallel 越线(默认线 2),入口段仍不出建议
    clone = os.path.join(tmp, "sug-clone")
    git(tmp, "clone", "-q", root, clone)
    for r in (root, clone):
        expect(nm(r, "docgen").returncode == 0, "⑧ docgen")
    expect("Suggest size" not in body(root), "⑧ 入口段里不应有升降档建议行: %r" % body(root))
    expect(read(root, "AGENTS.md") == read(clone, "AGENTS.md"), "⑧ 两个克隆生成的入口段应逐字节相同")


def main():
    tmp = tempfile.mkdtemp(prefix="nm-suggest-")
    try:
        for fn in (t_status_and_record, t_entry_line):
            print("== " + fn.__name__)
            fn(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("FAIL %d:" % len(fails))
        for f in fails:
            print(" - " + f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
