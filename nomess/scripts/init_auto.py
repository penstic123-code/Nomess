"""nomess init --auto [--lang en|zh-CN] [--size small|medium|large] / nomess off。
init --auto:init skill 里机械的步骤全在这里(零 token):nomess.json、AGENTS.md 的 nomess 段、CLAUDE.md 导入、.gitignore / .gitattributes、
<docs_root>/overview.md、refresh、check --freeze、hooks install;认出文档网站源目录时把它整体登记成对外文档(13.13)。已有文件只补缺的,重跑不改已有内容;不提交;会清掉 `git config nomess.auto false`。
最后只打一行给 AI 转述(新增了什么、冻结了多少、提交检查接上没有)。
退出码:0 完成,2 做不了(不在 git 仓库、分离头指针推不出主分支、--size 想调小)。
off:hooks uninstall + git config --local nomess.auto false,并列出 init 建过的文件供手删(不自动删)。"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys

import doctypes
import githook
import messages
import nm_config
import snapshot
from messages import t

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "init", "templates")
NL = chr(10)
M = {
    "IA_DONE": ("nomess enabled. Changed: %s. Froze %d existing findings in the baseline. %s Tell the user in one sentence; not committed.",
                "nomess 已启用。改动的文件:%s。存量冻结了 %d 条。%s 用一句话告诉用户;没有提交。"),
    "IA_NONE": ("nothing", "无"),
    "IA_WIRED": ("Commit checks are wired.", "提交检查已接上。"),
    "IA_NOT_WIRED": ("Commit checks are NOT wired (another hook manager owns the hooks): run `nomess hooks install` for the recipe.",
                     "提交检查没接上(已有别的钩子管理器):跑 `nomess hooks install` 看接线配方。"),
    "IA_DETACHED": ("detached HEAD: cannot tell the main branch; check out a branch or ask the user, then write main_branch in nomess.json",
                    "分离头指针,推不出主分支:先切到分支,或问用户后写进 nomess.json 的 main_branch"),
    "IA_SMALLER": ("--size %s is smaller than the current %s; going down switches checks off, which a person does (edit size in nomess.json, commit with --no-verify, label the PR nomess-loosen)",
                   "--size %s 比现在的 %s 小;调小会关掉检查,要人来做(改 nomess.json 的 size,用 --no-verify 提交,PR 打 nomess-loosen 标签)"),
    "IA_OFF": ("nomess is off for this repo (git hooks removed, nomess.auto=false). Files init created, delete by hand if wanted: %s",
               "nomess 已对这个仓库关闭(git 钩子已移除,nomess.auto=false)。init 建过的文件,要的话手删:%s"),
}
messages.add(M)
OFF_FILES = ("nomess.json", ".nomess-baseline.json", "%s/overview.md", "%s/system-map/", ".claude/rules/nomess/",
             "AGENTS.md (the nomess section)", "CLAUDE.md (@AGENTS.md line)", ".gitignore / .gitattributes (nomess lines)")


def _git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


def main_branch(root):
    """origin/HEAD -> 本地 main / master -> 当前分支(没有提交的新仓库也行);分离头指针返回 None。"""
    rc, out = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out:
        return out.split("/", 1)[-1]
    for b in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "-q", "refs/heads/" + b)[0] == 0:
            return b
    rc, out = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    return out if rc == 0 and out else None


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _template(lang, *parts):
    return _read(os.path.join(TEMPLATES, lang, *parts))


def _add_lines(path, lines):
    """补缺的行(整行比较);返回是否改了。"""
    old = _read(path)
    have = {l.strip() for l in (old or "").splitlines()}
    miss = [l for l in lines if l not in have]
    if not miss:
        return False
    body = old or ""
    if body and not body.endswith("\n"):
        body += "\n"
    nm_config.atomic_write(path, body + "\n".join(miss) + "\n")
    return True


def _fill_index(root, cfg_path, cfg, lang, put):
    """补目录段(老项目、新项目同一条路):docgen 缺 docs-index / lessons-index 项就加,文件缺或缺标记就补;只补缺,已有内容不动。返回是否改了 nomess.json。"""
    want = {"docs-index": nm_config.docs_root(cfg) + "/overview.md", "lessons-index": nm_config.lessons_dir(cfg) + "/README.md"}
    gen = cfg.get("docgen", {})
    missing = {n: f for n, f in want.items() if n not in gen}
    if missing:
        raw = json.loads(_read(cfg_path).lstrip(chr(0xFEFF)))
        raw.setdefault("docgen", {}).update({n: {"file": f, "builtin": n} for n, f in missing.items()})
        nm_config.atomic_write(cfg_path, json.dumps(raw, indent=2, ensure_ascii=False) + NL)
    for name, rel in want.items():
        rel = gen.get(name, {}).get("file", rel)
        text = _read(os.path.join(root, rel))
        mark = "<!-- GEN:%s BEGIN -->" % name
        if text is None:
            put(rel, _template(lang, "docs", "overview.md" if name == "docs-index" else "lessons/README.md"))
        elif mark not in text:
            put(rel, text + ("" if text.endswith(NL) else NL) + NL + mark + NL + "<!-- GEN:%s END -->" % name + NL)
    return bool(missing)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess init --auto", description="enable nomess in this repo without asking anything")
    ap.add_argument("--auto", action="store_true", required=True)
    ap.add_argument("--lang", choices=messages.LANGS, default="en")
    ap.add_argument("--size", choices=nm_config.SIZES)
    a = ap.parse_args(argv)
    root = snapshot.toplevel(os.getcwd())  # 不在 git 仓库抛 SnapshotError,入口转成退出 2
    os.chdir(root)
    cfg_path = os.path.join(root, nm_config.CONFIG_NAME)
    touched = []
    if os.path.isfile(cfg_path):
        cfg = nm_config.load(cfg_path)  # 同时设好提示语言
        lang = cfg.get("lang", "en")
        if a.size and nm_config.SIZES.index(a.size) != nm_config.SIZES.index(cfg.get("size", "small")):
            cur = cfg.get("size", "small")
            if nm_config.SIZES.index(a.size) < nm_config.SIZES.index(cur):
                print(t("IA_SMALLER", a.size, cur), file=sys.stderr)
                return 2
            text = _read(cfg_path)
            new, n = re.subn(r'("size"\s*:\s*)"[^"]*"', r'\1"%s"' % a.size, text, count=1)
            nm_config.atomic_write(cfg_path, new if n else json.dumps(dict(cfg, size=a.size), indent=2, ensure_ascii=False) + "\n")
            touched.append(nm_config.CONFIG_NAME)
    else:
        lang = a.lang
        messages.set_lang(lang)
        branch = main_branch(root)
        if branch is None:
            print(t("IA_DETACHED"), file=sys.stderr)
            return 2
        new = json.loads(_template(lang, "nomess.json"))
        new.update(main_branch=branch, size=a.size or "small", lang=lang)
        with snapshot.open_snapshot(root, "worktree") as snap:  # 工作区:新仓库可能还没有提交
            site = doctypes.site_dir(snap)
        if site:  # 网站源整体只读;源目录就是 docs/ 时项目文档另起一个根,开发文档不和网站混、也不会被发布
            new["public_docs"] = [site + "/**"]
            if site == "docs":
                new["docs_root"] = "project-docs"
                new["docgen"]["docs-index"]["file"] = "project-docs/overview.md"  # 模板按缺省根写的 docs/overview.md,换了根要跟着换
                new["docgen"]["lessons-index"]["file"] = "project-docs/lessons/README.md"
        nm_config.atomic_write(cfg_path, json.dumps(new, indent=2, ensure_ascii=False) + "\n")
        touched.append(nm_config.CONFIG_NAME)
        cfg = nm_config.load(cfg_path)

    def put(rel, text):
        nm_config.atomic_write(os.path.join(root, rel), text)
        touched.append(rel)

    block = _template(lang, "AGENTS-nomess.md")
    agents = _read(os.path.join(root, "AGENTS.md"))
    if agents is None:
        put("AGENTS.md", "# %s\n\n%s" % (os.path.basename(root), block))
    elif "<!-- GEN:nomess BEGIN -->" not in agents:  # 已有标记就不碰(多对标记留给人处理)
        put("AGENTS.md", agents + ("" if agents.endswith("\n") else "\n") + "\n" + block)
    claude = _read(os.path.join(root, "CLAUDE.md"))
    if claude is None:
        put("CLAUDE.md", "@AGENTS.md\n")
    elif "@AGENTS.md" not in (l.strip() for l in claude.splitlines()):
        put("CLAUDE.md", "@AGENTS.md\n" + claude)
    if _add_lines(os.path.join(root, ".gitignore"), [".nomess/"]):
        touched.append(".gitignore")
    docs = nm_config.docs_root(cfg)
    gitattrs = ["%s/system-map/** text eol=lf" % docs, ".claude/rules/nomess/** text eol=lf", "%s/inbox.md merge=union" % nm_config.lessons_dir(cfg)]
    if _add_lines(os.path.join(root, ".gitattributes"), gitattrs):
        touched.append(".gitattributes")
    if _fill_index(root, cfg_path, cfg, lang, put) and nm_config.CONFIG_NAME not in touched:
        touched.append(nm_config.CONFIG_NAME)

    import check
    frozen = io.StringIO()  # 子步骤的逐行输出不要:最后只给 AI 一行
    with contextlib.redirect_stdout(io.StringIO()):
        githook.main_refresh([])
    with contextlib.redirect_stdout(frozen):
        check.main(["--freeze"])
    n = int(re.search(r"\d+", frozen.getvalue()).group())  # "baseline frozen: N findings -> ..."
    with contextlib.redirect_stdout(io.StringIO()):
        githook.main_refresh([])  # 系统图首页要数冻结了几条
    wired = all(res in ("installed", "kept") for _, res in githook.install(root))
    _git(root, "config", "--local", "--unset", "nomess.auto")
    print(t("IA_DONE", ", ".join(touched) or t("IA_NONE"), n, t("IA_WIRED") if wired else t("IA_NOT_WIRED")))
    return 0


def main_off(argv):
    root = snapshot.toplevel(os.getcwd())
    docs = nm_config.DEFAULTS["docs_root"]
    try:
        docs = nm_config.docs_root(nm_config.load(nm_config.find_config(root)))  # 同时设好提示语言
    except FileNotFoundError:
        pass
    githook.uninstall(root)
    _git(root, "config", "--local", "nomess.auto", "false")
    print(t("IA_OFF", ", ".join(f.replace("%s", docs) for f in OFF_FILES)))
    return 0
