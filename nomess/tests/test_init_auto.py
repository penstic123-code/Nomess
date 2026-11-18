"""R4:会话开始钩子、init --auto、免弹窗放行(都在临时仓库里真跑 git;不碰真实的 ~/.claude)。
测边界:没启用的仓库出启用提示、nomess.auto=false 后静默、dream 替身两个分支;init --auto 重跑不改文件、分离头指针退出 2、清掉 nomess.auto;
guard 对本插件命令放行、带 && 不放行、记忆目录写入要 agent_id、中文路径能匹配。全过打印 OK,否则列出失败项并退出码 1。"""
import json
import os
import re
import subprocess
import sys
import tempfile
import types

from helpers import HERE, NOMESS, PLUGIN, digest, expect, fails, nm, put

SESSION = os.path.join(PLUGIN, "hooks", "session.py")
GUARD = os.path.join(PLUGIN, "hooks", "guard.py")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "CI"}
ENV.update(PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=ENV)


def run_hook(script, data, cwd, env=None):
    p = subprocess.run([sys.executable, script], input=json.dumps(data).encode("utf-8"), cwd=cwd, capture_output=True,
                       env=dict(ENV, **(env or {})))
    return p.stdout.decode("utf-8").strip()


def tree(root):
    return {os.path.relpath(os.path.join(r, f), root): digest(os.path.join(r, f))
            for r, ds, fs in os.walk(root) for f in fs if ".git" not in os.path.relpath(r, root).split(os.sep)}


def test_session(tmp):
    repo = os.path.join(tmp, "s1")
    os.makedirs(repo)
    git(repo, "init", "-q")
    out = run_hook(SESSION, {"cwd": repo}, repo)
    expect("init --auto" in out and os.path.join(PLUGIN, "scripts", "nomess.py") in out, "没启用的仓库应出启用提示: %r" % out)
    expect(run_hook(SESSION, {"cwd": repo}, repo, {"CLAUDE_PLUGIN_OPTION_AUTO_INIT": "false"}) == "", "auto_init 关应静默")
    expect(run_hook(SESSION, {"cwd": repo}, repo, {"CI": "1"}) == "", "CI 应静默")
    git(repo, "config", "--local", "nomess.auto", "false")
    expect(run_hook(SESSION, {"cwd": repo}, repo) == "", "nomess.auto=false 应静默")
    plain = os.path.join(tmp, "nogit-dir")
    os.makedirs(plain, exist_ok=True)
    expect(run_hook(SESSION, {"cwd": plain}, plain) == "", "不在 git 仓库应静默")
    # 已启用:dream 用替身
    sys.path.insert(0, os.path.join(PLUGIN, "hooks"))
    import session
    with open(os.path.join(repo, "nomess.json"), "w") as f:
        f.write('{"format": "nomess/1"}')
    git(repo, "config", "--local", "--unset", "nomess.auto")
    state = {"summary": "tidied", "due": True}
    sys.modules["dream"] = types.SimpleNamespace(take_summary=lambda r: state["summary"], due=lambda r: state["due"])
    expect(session.decide(repo, {}) == "Tell the user: tidied", "有总结应先转告")
    state["summary"] = None
    expect("nomess:dream" in (session.decide(repo, {}) or ""), "due 为真应让模型调 dream")
    state["due"] = False
    expect(session.decide(repo, {}) is None, "没事应无输出")


def test_init(tmp):
    repo = os.path.join(tmp, "i1")
    os.makedirs(os.path.join(repo, "src"))
    git(repo, "init", "-q")
    git(repo, "config", "--local", "nomess.auto", "false")
    with open(os.path.join(repo, "src", "a.py"), "w") as f:
        f.write("x = 1\n")
    p = nm(repo, "init", "--auto", "--lang", "en")
    expect(p.returncode == 0 and p.stdout.startswith("nomess enabled"), "init --auto 应成功并打一行: %r %r" % (p.stdout, p.stderr))
    expect(len(p.stdout.strip().splitlines()) == 1, "只该打一行")
    for rel in ("nomess.json", "AGENTS.md", "CLAUDE.md", "docs/overview.md", ".gitignore", ".gitattributes"):
        expect(os.path.isfile(os.path.join(repo, rel)), "缺 " + rel)
    expect(git(repo, "config", "--local", "nomess.auto").stdout.strip() == "", "应清掉 nomess.auto")
    expect(git(repo, "log").returncode != 0, "不该提交")
    before = tree(repo)
    p = nm(repo, "init", "--auto")
    expect(p.returncode == 0 and tree(repo) == before, "重跑不该改已有文件")
    p = nm(repo, "init", "--auto", "--size", "medium")
    expect(p.returncode == 0 and '"medium"' in open(os.path.join(repo, "nomess.json"), encoding="utf-8").read(), "调大应写进 nomess.json")
    p = nm(repo, "init", "--auto", "--size", "small")
    expect(p.returncode == 2, "调小应退出 2")
    p = nm(repo, "off")
    expect(p.returncode == 0 and git(repo, "config", "--local", "nomess.auto").stdout.strip() == "false", "off 应写 nomess.auto=false")
    # 分离头指针:没有 main / master 也没有 origin/HEAD
    d = os.path.join(tmp, "i2")
    os.makedirs(d)
    git(d, "init", "-q", "-b", "feature")
    git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    git(d, "checkout", "-q", "--detach")
    p = nm(d, "init", "--auto")
    expect(p.returncode == 2 and not os.path.exists(os.path.join(d, "nomess.json")), "分离头指针应退出 2 且不建文件")
    p = nm(os.path.join(tmp, "nogit-dir"), "init", "--auto")
    expect(p.returncode == 2, "不在 git 仓库应退出 2")


def test_init_old_config(tmp):
    """老项目:已有 nomess.json 没有 docs-index / lessons-index,init --auto 只补这两项和标记,其它不变。"""
    repo = os.path.join(tmp, "i4")
    os.makedirs(os.path.join(repo, "docs"))
    git(repo, "init", "-q")
    git(repo, "config", "--local", "nomess.auto", "false")
    cfg = {"format": "nomess/1", "main_branch": "main", "size": "small", "lang": "en", "systems": {}, "docgen": {"nomess": {"file": "AGENTS.md", "builtin": "agents-entry"}}}
    with open(os.path.join(repo, "nomess.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(repo, "docs", "overview.md"), "w", encoding="utf-8") as f:
        f.write("# Mine\n")
    p = nm(repo, "init", "--auto")
    expect(p.returncode == 0, "应成功: %r %r" % (p.stdout, p.stderr))
    new = json.load(open(os.path.join(repo, "nomess.json"), encoding="utf-8"))
    expect(new["docgen"]["docs-index"] == {"file": "docs/overview.md", "builtin": "docs-index"}, "应补 docs-index 项")
    expect(new["docgen"]["lessons-index"]["file"] == "docs/lessons/README.md", "应补 lessons-index 项")
    expect(new["docgen"]["nomess"] == cfg["docgen"]["nomess"] and new["systems"] == {}, "其它内容不变")
    ov = open(os.path.join(repo, "docs", "overview.md"), encoding="utf-8").read()
    expect(ov.startswith("# Mine\n") and "<!-- GEN:docs-index BEGIN -->" in ov, "overview 应保留原文并补标记")
    expect("<!-- GEN:lessons-index BEGIN -->" in open(os.path.join(repo, "docs", "lessons", "README.md"), encoding="utf-8").read(), "应建教训索引页")


def test_init_site(tmp):
    """13.13 自动识别:docs/ 是 mkdocs 源 -> docs_root 设成 project-docs、docs/** 进 public_docs,总览和系统图跟着新根走。"""
    repo = os.path.join(tmp, "i3")
    os.makedirs(os.path.join(repo, "docs"))
    git(repo, "init", "-q", "-b", "main")
    put(repo, "mkdocs.yml", "site_name: x\nnav:\n  docs_dir: nope\ndocs_dir: ./docs\n")  # 缩进的不是顶层键;./docs 要认成 docs
    put(repo, "docs/index.md", "# site\n")
    p = nm(repo, "init", "--auto", "--lang", "en")
    cfg = json.load(open(os.path.join(repo, "nomess.json"), encoding="utf-8"))
    expect(p.returncode == 0 and cfg.get("docs_root") == "project-docs" and cfg.get("public_docs") == ["docs/**"], "mkdocs 源在 docs/: %r %r" % (cfg, p.stderr))
    expect(os.path.isfile(os.path.join(repo, "project-docs", "overview.md")), "总览应建在 project-docs/")
    expect("project-docs/system-map/** text eol=lf" in open(os.path.join(repo, ".gitattributes"), encoding="utf-8").read(), ".gitattributes 跟新根")


def test_guard(tmp):
    repo = os.path.join(tmp, "中文 仓库")  # 中文和空格
    os.makedirs(repo)
    git(repo, "init", "-q")
    cfg = os.path.join(tmp, "cfg")
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(repo))
    mem = os.path.join(cfg, "projects", slug, "memory")
    os.makedirs(mem)
    env = {"CLAUDE_CONFIG_DIR": cfg}
    nomess = os.path.join(PLUGIN, "scripts", "nomess.py")

    def call(tool, inp, **extra):
        return run_hook(GUARD, dict({"tool_name": tool, "tool_input": inp, "cwd": repo}, **extra), repo, env)

    cmd = '"%s" "%s" check' % (sys.executable, nomess)
    expect('"allow"' in call("Bash", {"command": cmd}), "本插件命令应放行")
    expect('"allow"' in call("PowerShell", {"command": "& " + cmd}), "PowerShell 的 & 调用应放行")
    expect(call("Bash", {"command": cmd + " && echo hi"}) == "", "带 && 不应放行")
    expect(call("Bash", {"command": cmd + " > out.txt"}) == "", "带重定向不应放行")
    expect(call("Bash", {"command": cmd + " $(echo x)"}) == "", "带命令替换不应放行")
    expect(call("Bash", {"command": '"%s" other.py' % sys.executable}) == "", "别的脚本不应放行")
    f = os.path.join(mem, "note.md")
    expect(call("Write", {"file_path": f}, agent_id="") == "", "记忆目录写入 agent_id 为空不应放行")
    expect('"allow"' in call("Write", {"file_path": f}, agent_id="a1"), "记忆目录写入有 agent_id 应放行(中文路径)")
    expect(call("Write", {"file_path": os.path.join(mem, "x.py")}, agent_id="a1") == "", "记忆目录里的非 .md 不应放行")
    expect(call("Write", {"file_path": os.path.join(mem, "a", "b", "x.md")}, agent_id="a1") == "", "记忆目录第三层不应放行")
    expect(call("Write", {"file_path": os.path.join(repo, "src", "x.py")}, agent_id="a1") == "", "别处写入不应放行")
    open(os.path.join(repo, "nomess.json"), "w", encoding="utf-8").write('{"format": "nomess/1", "main_branch": "main", "lang": "zh-CN", "size": "medium"}')
    git(repo, "add", "nomess.json")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    git(repo, "worktree", "add", "--detach", os.path.join(repo, ".nomess", "dream"), "HEAD")
    dw = os.path.join(repo, ".nomess", "dream")
    expect('"allow"' in call("Edit", {"file_path": os.path.join(dw, "docs", "a.md")}), "dream 临时目录里 docs 下的 .md 应放行")
    expect(call("Edit", {"file_path": os.path.join(dw, "docs", "a.py")}) == "", "dream 临时目录里 docs 下的 .py 不应放行")
    expect(call("Edit", {"file_path": os.path.join(dw, "nomess.json")}) == "", "dream 临时目录里的 nomess.json 不应放行")
    expect(call("Edit", {"file_path": os.path.join(dw, ".git")}) == "", "dream 临时目录里的 .git 不应放行")
    expect(call("PowerShell", {"command": "& " + cmd + "\r(Start-Process calc)"}) == "", "命令里有 \r 不应放行")
    plain = os.path.join(tmp, "nogit-dir")
    os.makedirs(plain, exist_ok=True)
    expect(run_hook(GUARD, {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(plain, "a.md")}, "cwd": plain}, plain, env) == "", "非 git 目录里 guard 不放行也不抛")
    out_mem = os.path.join(tmp, "outmem")
    os.makedirs(out_mem, exist_ok=True)
    put(repo, ".claude/settings.json", json.dumps({"autoMemoryDirectory": out_mem}))
    expect(call("Write", {"file_path": os.path.join(out_mem, "n.md")}, agent_id="a1") == "", "记忆目录在 projects/ 之外不应放行")


def main():
    tmp = tempfile.mkdtemp(prefix="nomess-ia-")
    test_session(tmp)
    test_init(tmp)
    test_init_site(tmp)
    test_init_old_config(tmp)
    test_guard(tmp)
    print("OK" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
