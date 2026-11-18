"""P21 棘轮和检测器接口的测试:每条在临时 git 仓库里真跑(不装钩子)。只测读代码难推准、又容易回归的边界行为;
其余验收在交回里写"读代码确认"。全过打印 OK,否则列出失败项并退出码 1。可在命令行只跑指定的用例(t_ 开头的函数名)。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from helpers import expect, fails, mkrepo, nm, put  # noqa: E402
import check  # noqa: E402
import snapshot  # noqa: E402

# 假检测器(四个包共用的契约):X1 是次数类(每行 SWALLOW 一条),X2 是指标类(行数超过 eff 的 smells.file_lines)
FAKE = '''import nm_config
RULES = [{"id": "X1", "level": "red", "what": "CFG1_HINT", "why": "CFG1_HINT"},
         {"id": "X2", "level": "red", "what": "CFG1_HINT", "why": "CFG1_HINT"}]


def run(snap, changes, eff):
    out = []
    for p, st in sorted(changes.items()):
        if st == "D" or not p.endswith(".py"):
            continue
        lines = snap.text(p).split("\\n")
        out += [nm_config.F("red", "X1", p, i, l, "swallow", k=[]) for i, l in enumerate(lines, 1) if "SWALLOW" in l]
        n = len([l for l in lines if l.strip()])
        if n > eff(p)["smells"]["file_lines"]:
            out.append(nm_config.F("red", "X2", p, 0, p, "long %d" % n, k=[], metric=n))
    return out
'''
RULE = {"id": "R1", "level": "red", "what": "w", "why": "y", "glob": "src/**", "forbid": "BAD"}


def git(root, *a):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr))
    return p.stdout.strip()


def commit(root, msg="c"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", msg)
    return git(root, "rev-parse", "HEAD")


def cfg_put(root, cfg):
    put(root, "nomess.json", json.dumps(dict({"format": "nomess/1", "main_branch": "main", "lang": "en", "size": "medium"}, **cfg)))


def run(root, **kw):
    """工作区对 HEAD,和手动 nomess check 一样。"""
    with snapshot.open_snapshot(root, "worktree") as cand:
        base = snapshot.open_snapshot(root, "tree", "HEAD") if snapshot.has_commit(root, "HEAD") else None
        try:
            return check.evaluate(cand, base, exec_cmd=True, full=True, **kw)
        finally:
            if base:
                base.close()


def freeze(root):
    with snapshot.open_snapshot(root, "worktree") as snap:
        base = snapshot.open_snapshot(root, "tree", "HEAD") if snapshot.has_commit(root, "HEAD") else None
        try:
            text, _n, bp = check.rebaseline(snap, base, "freeze", True)
        finally:
            if base:
                base.close()
    put(root, bp, text)


def gate(root):
    """和钩子一样:索引对 HEAD,旧检查只跑可能变红的。"""
    git(root, "add", "-A")
    with snapshot.open_snapshot(root, "index") as cand, snapshot.open_snapshot(root, "tree", "HEAD") as base:
        return check.evaluate(cand, base, exec_cmd=True, gate=True)


def by(res, rule):
    return [f for f in res["findings"] if f["rule"] == rule]


def lines(n, extra=""):
    return "".join("x%d = %d\n" % (i, i) for i in range(n)) + extra


def t_fake_detector_flow(tmp):
    """① 假检测器的发现走完:新增判红 -> 冻结 -> 存量 frozen -> 次数多一条只新的那条红 -> 指标涨在 grow_slack 内黄、超了红 -> B1。"""
    put(tmp, "fake_det.py", FAKE)
    check.DETECTORS.append("fake_det")
    try:
        root = mkrepo(tmp, "flow", {"lang": "en"}, [("src/a.py", "SWALLOW\n"), ("src/big.py", lines(900))])
        res = run(root)
        expect({(f["rule"], f["level"], f["state"]) for f in res["findings"] if f["rule"] in ("X1", "X2")} ==
               {("X1", "red", "new"), ("X2", "red", "new")} and check.blocking(res), "冻结前:X1、X2 都是新增红")
        freeze(root)
        commit(root)
        res = run(root)
        fs = by(res, "X1") + by(res, "X2")
        expect(len(fs) == 2 and all(f["state"] == "frozen" and f["frozen"] and f["level"] == "yellow" for f in fs)
               and not check.blocking(res), "冻结后:存量黄 frozen,不挡: %r" % [(f["rule"], f["state"]) for f in fs])
        put(root, "src/a.py", "SWALLOW\nSWALLOW\n")
        put(root, "src/big.py", lines(950))
        res = run(root)
        x1 = sorted((f["line"], f["state"], f["level"]) for f in by(res, "X1"))
        expect(x1 == [(1, "frozen", "yellow"), (2, "new", "red")], "次数类多一条:只有后面那条新增红: %r" % x1)
        expect([(f["state"], f["level"]) for f in by(res, "X2")] == [("grew", "yellow")], "指标涨 950/900 在 10% 内:grew 黄")
        put(root, "src/big.py", lines(1000))
        expect([(f["state"], f["level"]) for f in by(run(root), "X2")] == [("worse", "red")], "指标涨 1000/900 超 10%:worse 红")
        bl = json.load(open(os.path.join(root, ".nomess-baseline.json"), encoding="utf-8"))
        bl["rules"]["X1"][0]["n"] = 5
        put(root, ".nomess-baseline.json", json.dumps(bl))
        expect(any(f["level"] == "red" for f in by(run(root), "B1")), "已有规则号下把次数调大:B1 红")
    finally:
        check.DETECTORS.remove("fake_det")


def t_b2_cannot_bypass(tmp):
    """② B2 绕不过去:check.builtin 补写 [];正则改窄;给还不存在的 src/new/** 加 off 的 scope。"""
    root = mkrepo(tmp, "b2", {"lang": "en", "check": {"rules": [RULE]}}, [("src/a.py", "ok\n")])
    commit(root)
    for change, what in (({"check": {"rules": [RULE], "builtin": []}}, "builtin 写成 []"),
                         ({"check": {"rules": [dict(RULE, forbid="BADX")]}}, "正则改窄"),
                         ({"check": {"rules": [RULE]}, "scopes": [{"paths": ["src/new/**"], "off": True, "why": "w"}]}, "新目录 off")):
        cfg_put(root, change)
        expect(any(f["level"] == "red" for f in by(run(root), "B2")), "B2 应红:" + what)


def t_systems_change(tmp):
    """③ systems 的任何改动(新子系统)都是 B2。"""
    root = mkrepo(tmp, "sys", {"lang": "en", "systems": {"core": ["src/**"]}}, [("src/a.py", "ok\n")])
    commit(root)
    cfg_put(root, {"systems": {"core": ["src/**"], "ui": ["ui/**"]}})
    expect(any(f["level"] == "red" for f in by(run(root), "B2")), "新子系统:B2 红")


def t_first_freeze(tmp):
    """④ 基准已启用、基线里没有的号,连同冻结一起带上新违规 -> B1 红;新登记的号首次冻结 -> 不报。"""
    root = mkrepo(tmp, "ff", {"lang": "en", "check": {"rules": [RULE]}}, [("src/a.py", "ok\n")])
    commit(root)
    put(root, "src/a.py", "BAD\n")
    freeze(root)
    expect(any(f["level"] == "red" for f in by(run(root), "B1")), "基准已启用的 R1 现在才冻结:B1 红")
    root = mkrepo(tmp, "ff2", {"lang": "en", "check": {"rules": [RULE]}}, [("src/a.py", "ok\n"), ("src/b.py", "OLD\n")])
    commit(root)
    cfg_put(root, {"check": {"rules": [RULE, dict(RULE, id="R2", forbid="OLD")]}})
    freeze(root)
    res = run(root)
    expect(not by(res, "B1") and not check.blocking(res) and "R2" in res["new_frozen"], "新登记的 R2 首次冻结:不报、列进 new_frozen: %r" % [(f["rule"], f["msg"]) for f in res["findings"]])


def t_ci(tmp):
    """⑤ --ci:提交里同时带新违规和写进基线 -> 红;加 --allow-loosen -> 通过,B1 以黄列出。"""
    root = mkrepo(tmp, "ci", {"lang": "en", "check": {"rules": [RULE]}}, [("src/a.py", "ok\n")])
    nm(root, "check", "--freeze")
    base = commit(root)
    put(root, "src/a.py", "BAD\n")
    bl = json.load(open(os.path.join(root, ".nomess-baseline.json"), encoding="utf-8"))
    bl["rules"]["R1"] = [{"file": "src/a.py", "k": [], "level": "red", "n": 1}]
    put(root, ".nomess-baseline.json", json.dumps(bl))
    commit(root)
    p = nm(root, "check", "--ci", "--base", base, "--json")
    expect(p.returncode == 1 and any(i["rule"] == "B1" and i["level"] == "red" for i in json.loads(p.stdout)), "--ci:B1 红")
    p = nm(root, "check", "--ci", "--base", base, "--allow-loosen", "--json")
    items = json.loads(p.stdout) if p.stdout.strip() else []
    expect(p.returncode == 0 and any(i["rule"] == "B1" and i["level"] == "yellow" for i in items), "--allow-loosen:通过,B1 黄")


def t_config_deleted(tmp):
    """⑥ 基准有 nomess.json、待检删了 -> B2 红。"""
    root = mkrepo(tmp, "del", {"lang": "en"}, [("src/a.py", "ok\n")])
    commit(root)
    os.remove(os.path.join(root, "nomess.json"))
    res = run(root)
    expect([(f["rule"], f["level"]) for f in res["findings"]] == [("B2", "red")], "删掉配置:B2 红")


def t_scopes(tmp):
    """⑦ src/save/** 设 file_lines 400:那里 500 行的新文件红,别处不报(具体度合并)。"""
    put(tmp, "fake_det.py", FAKE)
    check.DETECTORS.append("fake_det")
    try:
        root = mkrepo(tmp, "scope", {"lang": "en", "scopes": [{"paths": ["src/save/**"], "smells": {"file_lines": 400}, "why": "w"}]},
                      [("src/save/x.py", lines(500)), ("src/other.py", lines(500))])
        x2 = [(f["file"], f["level"]) for f in by(run(root), "X2")]
        expect(x2 == [("src/save/x.py", "red")], "X2 只报 src/save/x.py: %r" % x2)
    finally:
        check.DETECTORS.remove("fake_det")


def t_unexecuted_rule_no_credit(tmp):
    """审查 1:没在本轮执行的号(--no-exec 时的 cmd 规则)不能首次冻结拿额度 -> B1。"""
    root = mkrepo(tmp, "noexec", {"lang": "en"}, [("src/a.py", "ok\n")])
    commit(root)
    cfg_put(root, {"check": {"rules": [{"id": "C9", "level": "red", "what": "w", "why": "y", "cmd": ["git", "--no-such-flag"]}]}})
    put(root, ".nomess-baseline.json", check.dump_baseline({"C9": {("red", (), ("whatever",)): ("n", 1)}}))
    with snapshot.open_snapshot(root, "worktree") as cand, snapshot.open_snapshot(root, "tree", "HEAD") as base:
        res = check.evaluate(cand, base, exec_cmd=False, full=True)
    expect(any(f["rule"] == "B1" and f["level"] == "red" for f in res["findings"]), "没执行的 C9 首次冻结:B1 红")


def t_glob_whitespace(tmp):
    """审查 2:给 scope 的 glob 加前导空格不改变具体度(解析时规范化一次)。"""
    import nm_config
    cfg = nm_config.parse(json.dumps({"format": "nomess/1", "main_branch": "main", "scopes": [
        {"paths": ["          src/**"], "off": True, "why": "a"}, {"paths": ["src/a.py"], "off": False, "why": "b"}]}), "x")
    expect(nm_config.Effective(cfg)("src/a.py")["off"] is False, "更具体的 src/a.py 仍然覆盖 src/**")


def t_gate_cmd_dirty(tmp):
    """审查 5:钩子里已跟踪文件有未暂存改动时 cmd 规则不跑,报黄 CMD1;工作区干净时照跑。"""
    root = mkrepo(tmp, "gatecmd", {"lang": "en", "check": {"rules": [
        {"id": "C1", "level": "red", "what": "w", "why": "y", "cmd": ["git", "--no-such-flag"]}]}}, [("src/a.py", "ok\n")])
    commit(root)
    put(root, "src/a.py", "staged\n")
    expect(any(f["rule"] == "C1" and f["level"] == "red" for f in gate(root)["findings"]), "干净时 cmd 规则照跑:C1 红")
    with open(os.path.join(root, "src", "a.py"), "a", encoding="utf-8") as f:
        f.write("draft\n")
    with snapshot.open_snapshot(root, "index") as cand, snapshot.open_snapshot(root, "tree", "HEAD") as base:
        res = check.evaluate(cand, base, exec_cmd=True, gate=True)
    expect(not by(res, "C1") and [f["level"] for f in by(res, "CMD1")] == ["yellow"], "有未暂存改动:C1 不跑,CMD1 黄")


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-ratchet-")
    sys.path.insert(0, tmp)  # 假检测器写在这里
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("t_") and callable(fn) and (not sys.argv[1:] or name in sys.argv[1:]):
                print("-- " + name)
                try:
                    fn(tmp)
                except Exception as e:  # noqa: BLE001 测试脚本:任何异常都算这条失败
                    fails.append("%s 抛异常: %r" % (name, e))
                    print("   ERROR: %r" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if not fails else "FAILED:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
