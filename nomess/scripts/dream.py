"""自动整理(dream)的脚本部分(设计稿 13.2 C、13.7、13.10、13.11)。零 token;模型只在临时 worktree 和记忆目录里动手,落地全在这里。
  due(root)            钩子在会话开始时调:只读文件和少量 git 命令,该不该整理。
  take_summary(root)   取出并清掉上次整理留下、还没告诉用户的那句总结。
  main(argv)           begin | git-log <词> | land | abort
为什么临时 worktree:整理要几分钟,这期间主会话会改文件、`git add -A`,半成品会被卷进用户的提交。
为什么落地前脚本自己查暂存区和未提交改动:实测 `cherry-pick -n` 在主检出有暂存内容时照样执行,git 不会替我们拒绝(13.7 第 6 条)。
状态 <git 公共目录>/nomess-dream.json(各 worktree 共用):last_attempt(YYYY-MM-DD)、fingerprint、backlog、landed_once、summary。
退出码:0 完成(land 放弃也是 0,原因在输出里),2 用法或前置条件不对,3 锁被占。"""
import datetime
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time

import arch
import check
import doctypes
import lessons
import map as nm_map
import messages
import nm_config
import plancheck
import snapshot
import status
from messages import t

LOCK, STATE = "nomess-dream.lock", "nomess-dream.json"
LOCK_TTL = 2 * 3600  # 超过 2 小时算上次死掉的
NET_DELETE_MAX = 60  # 一次整理净删(删行 − 增行)超过它就整次丢弃。推定值,按实际调(设计稿 13.14)
LIST_MAX = 3  # 总结里被删页、缩得最多的页各列几个
NOTES = os.path.join(".nomess", "dream-notes.md")
NOMESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nomess.py")
CONVENTION = {"README", "CHANGELOG", "LICENSE", "CONTRIBUTING", "CODE_OF_CONDUCT", "SECURITY", "AGENTS", "CLAUDE"}  # 惯例文件(任何层的同名 .md)不接管
GAP = re.compile(r"^(?:文档缺口|doc gap)\s*[:：]", re.I)
GEN_BLOCK = re.compile(r"<!-- GEN:(.+?) BEGIN -->.*?<!-- GEN:\1 END -->", re.S)

M = {
    "DR_BUSY": ("another dream is running (lock held); try later", "已有另一次整理在跑(锁被占),稍后再试"),
    "DR_NOBEGIN": ("no dream in progress: run `nomess dream begin` first", "没有进行中的整理:先跑 `nomess dream begin`"),
    "DR_LIST": ("dream work list (%d items)", "整理工作清单(%d 条)"),
    "DR_MORE": ("%d more items next time", "还有 %d 条下次"),
    "DR_ALIAS": ("%d lesson entries have no aliases", "%d 条教训缺别名"),
    "DR_WT": ("worktree (edit docs and lessons here): %s", "worktree(在这里改文档和教训):%s"),
    "DR_MEM": ("memory directory: %s", "记忆目录:%s"),
    "DR_MEM_NONE": ("memory directory: not located, tidy only the project", "记忆目录:没定位到,只整理项目"),
    "DR_MV_REFUSED": ("refused: %s", "拒绝:%s"),
    "DR_NOTES_AT": ("write items that need a person's decision to %s, one per line", "要人定的写进 %s,一行一条"),
    "DR_K_inbox": ("inbox", "inbox"), "DR_K_near": ("near-duplicate titles", "标题近似"),
    "DR_K_unverified": ("unverified", "未核实"), "DR_K_memory": ("memory over budget", "记忆超预算"),
    "DR_K_doc4": ("DOC4 misplaced", "DOC4 放错位置"), "DR_K_doc5": ("DOC5 orphans", "DOC5 孤儿页"),
    "DR_K_doc6": ("DOC6 too long", "DOC6 超长"), "DR_K_plans": ("plans (PL-DUP / PL-STALE / PLN2)", "方案(PL-DUP / PL-STALE / PLN2)"),
    "DR_K_merged": ("schedule rows already merged (move into their plan's change log)", "排期里已合的行(挪进所属方案的变更记录)"),
    "DR_K_strays": ("stray .md outside the docs root (take over)", "文档根外的散落 .md(接管)"),
    "DR_K_stale": ("stale references: the path no longer exists", "过时引用:提到的路径已不存在"),
    "DR_STALE_project": ("fix", "改"), "DR_STALE_dev": ("may fix in place", "可就地改"), "DR_STALE_public": ("notes only", "只写 notes"),
    "DR_K_gaps": ("doc gaps", "文档缺口"),
    "DR_NOCHANGE": ("dream: nothing changed, nothing to land", "整理:没有改动,不用落地"),
    "DR_DISCARD": ("dream discarded: %s", "整理已丢弃:%s"),
    "DR_REFRESH": ("`nomess refresh` failed in the worktree: %s", "worktree 里 `nomess refresh` 失败:%s"),
    "DR_FORBID": ("touches a path dream may not change: %s", "改了整理不许碰的路径:%s"),
    "DR_AGENTS": ("AGENTS.md changed outside the nomess generated section", "AGENTS.md 在 nomess 生成段之外有改动"),
    "DR_EXTERNAL": ("external-source entry %r was verified or lost its source line", "外部来源条目 %r 被改成已核实或去掉了来源行"),
    "DR_CHECK": ("`nomess check` has red: %s", "`nomess check` 有红:%s"),
    "DR_COMMIT": ("commit in the worktree was refused: %s", "worktree 里的提交被拒绝:%s"),
    "DR_GITOP": ("the main checkout is in the middle of a git operation (detached HEAD, merge, rebase, ...): %s", "主检出正处于进行中的 git 操作(分离头指针、合并、变基等):%s"),
    "DR_NOVERIFY": ("new entry %r is marked verified while an external-source entry lost its title key", "外部来源条目的标题键消失,同时新增了已核实条目 %r"),
    "DR_RM_WT": ("warning: could not remove the dream worktree %s: %s", "警告:没能删掉整理的 worktree %s:%s"),
    "DR_MEM_SKIP": ("memory directory is not in the default place and is not a git repository: memory not tidied", "记忆目录不在缺省位置且不是 git 仓库,未整理"),
    "DR_MEM_FAIL": ("memory commit failed: %s", "记忆提交失败:%s"),
    "DR_STAGED": ("the main checkout has staged changes", "主检出有已暂存内容"),
    "DR_DIRTY": ("the main checkout has uncommitted changes in files this commit touches: %s", "主检出里这次提交要碰的文件有未提交改动:%s"),
    "DR_PICK": ("cherry-pick failed (conflict or refused): %s", "cherry-pick 没成功(冲突或被拒):%s"),
    "DR_SUM": ("nomess tidied lessons and docs: moved %d, merged or removed %d, archived %d, rewritten %d; undo `git revert %s`%s",
               "nomess 整理了教训和文档:挪 %d、合并或删 %d、归档 %d、改写 %d;撤回 `git revert %s`%s"),
    "DR_SUM_FIRST": ("takeover tidy: moved %d, merged %d, archived %d, unsorted %d; undo `git revert %s`%s",
                     "接管整理:挪了 %d、合并 %d、归档 %d、未归类 %d;撤回 `git revert %s`%s"),
    "DR_SUM_MEM": ("; memory: `git -C %s revert %s`", ";记忆:`git -C %s revert %s`"),
    "DR_SUM_ONLY_MEM": ("nomess tidied memory (project side discarded: %s); undo `git -C %s revert %s`",
                        "nomess 整理了记忆(项目侧已丢弃:%s);撤回 `git -C %s revert %s`"),
    "DR_SUM_NOTES": ("; %d items wait for you, see .nomess/dream-notes.md", ";有 %d 条等你定,见 .nomess/dream-notes.md"),
    "DR_MSG": ("nomess dream: moved %d, merged or removed %d, archived %d, rewritten %d", "nomess dream: 挪 %d、合并或删 %d、归档 %d、改写 %d"),
    "DR_PRE": ("pre-dream snapshot", "pre-dream snapshot"),
    "DR_SEP": ("; ", ";"),
    "DR_GONE": ("deleted: %s", "删了:%s"),
    "DR_SHRUNK": ("shrunk most: %s", "缩得最多:%s"),
    "DR_ETC": (" and %d more", "等 %d 个"),
    "DR_SHOW": ("see what changed: `git show --stat %s`", "看改了什么:`git show --stat %s`"),
    "DR_NET": ("wanted to delete a net %d lines, over %d: %s", "想净删 %d 行,超过 %d:%s"),
    "DR_NET_NOTE": ("%d. dream wanted to delete a net %d lines: %s; to do it run `/nomess:dream apply %d`",
                    "%d. 整理想净删 %d 行:%s;要执行敲 `/nomess:dream apply %d`"),
    "DR_NET_MEM": ("; the memory changes were reverted", ";记忆改动已撤回"),
    "DR_NO_NET": ("this run may not delete a net amount: only merge, move, archive and rewrite; whatever you delete, add back",
                  "本次不许净删:只合并、挪、归档、改写,删多少补多少"),
    "DR_MEM_MSG": ("dream: memory tidy", "dream: 整理记忆"),
}
messages.add(M)


class DreamError(snapshot.SnapshotError):
    pass


# ---------------------------------------------------------------- git 小工具

def _ident(cwd):
    """没配提交身份时给一个兜底身份(整理的提交不该因此失败);配了就不覆盖用户的。"""
    p = subprocess.run(["git", "config", "user.email"], cwd=cwd, capture_output=True, text=True)
    return [] if p.stdout.strip() else ["-c", "user.name=nomess", "-c", "user.email=nomess@localhost"]


def _run(cwd, *args, ident=False):
    """(退出码, 标准输出去尾部空白, 标准错误去首尾空白);参数是列表,不经 shell。输出不去开头的空白:`status --porcelain` 的第一列可能是空格。"""
    p = subprocess.run(["git", *(_ident(cwd) if ident else []), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.rstrip(), p.stderr.strip()


def _must(cwd, *args, ident=False):
    rc, out, err = _run(cwd, *args, ident=ident)
    if rc:
        raise DreamError("git %s: %s" % (" ".join(args[:2]), err or out))
    return out


def _common(root):
    return os.path.normpath(_must(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))


def wt_path(base):
    """整理 worktree 的位置,全插件唯一的来源(dream、guard 都调它):<base 所在 worktree 的顶层>/.nomess/dream。
    不放进 .git 目录:那是 Claude Code 的受保护路径,放进去每次编辑都弹窗。base 本身就在整理 worktree 里时返回它自己。"""
    top = snapshot.toplevel(base)
    return top if top.endswith("/.nomess/dream") else os.path.join(top, ".nomess", "dream")


_wt = wt_path


def _today():
    return datetime.date.today().isoformat()


def _root():
    """项目根:从当前目录往上找 nomess.json;AI 的当前目录常在临时 worktree 里,这时回到它所属的主检出。"""
    top = os.path.dirname(nm_config.find_config())
    return os.path.dirname(os.path.dirname(top)) if os.path.normpath(top).replace("\\", "/").endswith("/.nomess/dream") else top


# ---------------------------------------------------------------- 状态

def _state(root):
    s = {"last_attempt": "", "fingerprint": "", "backlog": False, "landed_once": False, "summary": None, "next_check": "", "no_net_delete": False}
    p = os.path.join(_common(root), STATE)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            s.update(json.load(f))
    return s


def _save(root, s):
    nm_config.atomic_write(os.path.join(_common(root), STATE), json.dumps(s, ensure_ascii=False))


def take_summary(root):
    """取出并清掉上次整理留下的总结;没有返回 None。"""
    s = _state(root)
    if not s["summary"]:
        return None
    out, s["summary"] = s["summary"], None
    _save(root, s)
    return out


# ---------------------------------------------------------------- 信号

def strays(snap, exp):
    """接管候选(13.10):文档根外被跟踪的 .md,排除惯例文件(任何层的同名,含源码目录里各包自己的 README)、隐藏目录里的、教训库目录里的、
    开发者文档和对外文档(13.13:这两档不挪)、归属到某个子系统的(systems 或推出来的顶层目录:那是子系统自己的说明)、
    和被跟踪的非 .md 文件同目录的(跟着源码走的说明,挪走就和代码分家)。仓库根不算后一条:根上总有 nomess.json 之类。"""
    lessons_dir = exp["lessons_dir"] + "/"
    tier = doctypes.tier_of(exp, doctypes.site_dir(snap))
    owned = arch.ownership(snap, exp)
    code_dirs = {posixpath.dirname(p) for p in snap.files() if not p.endswith(".md")} - {""}
    return [p for p in snap.ls("", ".md", True)
            if not p.startswith((exp["docs_root"] + "/", lessons_dir)) and not tier(p) and not any(c.startswith(".") for c in p.split("/")[:-1])
            and posixpath.splitext(posixpath.basename(p))[0].upper() not in CONVENTION
            and p not in owned and posixpath.dirname(p) not in code_dirs]


def _tree_hash(root, rel):
    rc, out, _ = _run(root, "rev-parse", "-q", "--verify", "HEAD:" + rel)
    return out if rc == 0 else ""


def _fingerprint(root, exp, snap):
    """教训目录和文档根的树哈希 + 记忆目录的文件名和大小 + 散落 .md 清单 + 全部被跟踪文件路径清单的哈希:这些没变,再整理也是白跑。
    路径清单要算进来:源码删了文件、文档一字没动时,过时引用也会变。"""
    mem = status.memory_location(root)["dir"]
    files = []
    for dp, dirs, fs in os.walk(mem) if mem else ():
        dirs[:] = [d for d in dirs if d != ".git"]
        files += [[os.path.relpath(os.path.join(dp, f), mem).replace("\\", "/"), os.path.getsize(os.path.join(dp, f))] for f in fs]
    raw = json.dumps([_tree_hash(root, exp["lessons_dir"]), _tree_hash(root, exp["docs_root"]), sorted(files), strays(snap, exp),
                      hashlib.sha1("\0".join(sorted(snap.files())).encode("utf-8")).hexdigest()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def updated(e):
    """条目的更新日期;不是 YYYY-MM-DD 返回 None。"""
    return datetime.date.fromisoformat(e["updated"]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["updated"] or "") else None


def scan(root, snap, cfg, exp, st):
    """(items, hot):items 是 类 -> [一行描述](工作清单用,顺序固定),hot 是到线的类。due 和 begin 共用,只读。"""
    d, dr = exp["lessons_dir"], exp["dream"]
    ents = lessons.snapshot_entries(snap, d)
    today = datetime.date.today()
    inbox = [e for e in ents if e["file"] == lessons.INBOX]
    age = lambda e: (today - updated(e)).days if updated(e) else 0  # 手写的日期认不出就当 0 天
    items, hot = {}, set()
    items["inbox"] = ["%s (%dd)" % (e["title"], age(e)) for e in inbox]
    if len(inbox) >= exp["lessons_remind"] or any(age(e) >= dr["stale_days"] for e in inbox):
        hot.add("inbox")
    pairs = lessons.near_pairs([e["title"] for e in ents], exp["memory"]["title_ratio"])
    items["near"] = ["%s ~ %s" % (ents[i]["title"], ents[j]["title"]) for i, j in pairs]
    if len(pairs) >= 3:
        hot.add("near")
    unv = [e for e in ents if not e["verified"] and not lessons.is_external(e)]
    items["unverified"] = ["%s [%s]" % (e["title"], e["file"]) for e in unv if e["file"] != lessons.INBOX]
    if len(unv) >= 10:
        hot.add("unverified")
    mem = status.memory_location(root)["dir"]
    over = [f for f in check.memory_check(mem, cfg) if f["rule"] in ("M2", "M3")] if mem else []
    items["memory"] = ["%s %s: %s" % (f["rule"], f["file"], f["msg"]) for f in over]
    if over:
        hot.add("memory")
    bad = doctypes.misplaced(snap, exp)
    items["doc4"] = bad
    if len(bad) >= 5:
        hot.add("doc4")
    items["doc5"] = [f["msg"] for f in doctypes.doc5(snap, exp)]
    items["doc6"] = [f["msg"] for f in doctypes.doc6(snap, exp)]
    if items["doc6"]:
        hot.add("doc6")
    items["plans"] = []  # PL-DUP 等要跑 check,只在 begin 里补(due 要快)
    items["merged"] = [p["pkg"] for p in plancheck.schedule(snap, exp)[0] if p["state"] == "merged"]
    if items["merged"]:
        hot.add("merged")
    items["strays"] = strays(snap, exp)
    if items["strays"]:
        hot.add("strays")
    # 过时引用只进清单、不单独算到线:它随源码变化随时出现,单独到线会让整理跟着每次删文件跑
    items["stale"] = ["%s:%d `%s` (%s)" % (rel, n, p, t("DR_STALE_" + tier)) for tier, rel, n, p in doctypes.stale_refs(snap, exp)]
    items["gaps"] = [e["title"] for e in ents if GAP.match(e["title"])]
    if items["gaps"]:
        hot.add("gaps")
    if st["backlog"]:
        hot.add("backlog")
    return items, hot


def due(root):
    """该不该整理:dream.auto 开着、HEAD 里有 nomess.json、不是分离头指针、距上次尝试 ≥1 天、指纹变过、且任一信号到线。"""
    if _run(root, "symbolic-ref", "-q", "HEAD")[0] or _run(root, "cat-file", "-e", "HEAD:" + nm_config.CONFIG_NAME)[0]:
        return False
    st = _state(root)
    lock = os.path.join(_common(root), LOCK)
    if st["last_attempt"] >= _today() or (os.path.isfile(lock) and time.time() - os.path.getmtime(lock) < LOCK_TTL):
        return False
    with snapshot.open_snapshot(root, "tree", "HEAD") as snap:
        cfg = nm_config.load_snapshot(snap)
        exp = nm_config.expanded(cfg)
        if not exp["dream"]["auto"]:
            return False
        fp = _fingerprint(root, exp, snap)
        if st["fingerprint"] and fp == st["fingerprint"] and (not st["next_check"] or _today() < st["next_check"]):
            return False
        hot = bool(scan(root, snap, cfg, exp, st)[1])
        dates = [updated(e) for e in lessons.snapshot_entries(snap, exp["lessons_dir"]) if e["file"] == lessons.INBOX]
        dates = [d for d in dates if d]
        nxt = (min(dates) + datetime.timedelta(days=exp["dream"]["stale_days"])).isoformat() if dates else ""
    if not hot:  # 没到线也记下指纹和日期:内容没变就不必每个会话重扫;inbox 最老条目到 stale_days 那天再判一次
        st.update(last_attempt=_today(), fingerprint=fp, next_check=nxt)
        _save(root, st)
    return hot


# ---------------------------------------------------------------- 锁和临时 worktree

def _remove_wt(root, wt=None):
    wt = wt or wt_path(root)
    if os.path.isdir(wt):
        _run(root, "worktree", "remove", "--force", wt)
        if os.path.isdir(wt):
            shutil.rmtree(wt)
    _run(root, "worktree", "prune")


def _acquire(root):
    """独占创建锁文件,成功 True,被占 False;锁超过 2 小时算死锁,清掉并删旧 worktree 后再抢一次。"""
    p = os.path.join(_common(root), LOCK)
    for _ in range(2):
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            if time.time() - os.path.getmtime(p) < LOCK_TTL:
                return False
            _remove_wt(root, (_lock_data(root) or {}).get("wt"))  # 删锁里记的那个 worktree,不是当前算出来的
            os.remove(p)
    return False


def _release(root):
    p = os.path.join(_common(root), LOCK)
    if os.path.isfile(p):
        os.remove(p)


def _lock_data(root):
    """锁文件里的内容;读不出(空文件、坏 JSON)返回 None,调用方按死锁处理。"""
    try:
        with open(os.path.join(_common(root), LOCK), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _count_notes(root):
    p = os.path.join(root, NOTES)
    if not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ---------------------------------------------------------------- 记忆目录

def _mem_own_repo(mem):
    """记忆目录自己就是仓库。在别的仓库里面返回 False(不往别人的仓库里提交)。"""
    rc, top, _ = _run(mem, "rev-parse", "--show-toplevel")
    return rc == 0 and os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(mem))


def _mem_commit(mem, msg):
    """记忆仓库有改动就提交一次,返回提交号;没有改动返回 None。"""
    _must(mem, "add", "-A", "--", ".")
    if _run(mem, "diff", "--cached", "--quiet")[0] == 0:
        return None
    _must(mem, "commit", "-q", "-m", msg, ident=True)
    return _must(mem, "rev-parse", "HEAD")


def _under_claude(mem):
    d = os.path.normcase(os.path.realpath(status.claude_dir()))
    return os.path.normcase(os.path.realpath(mem)).startswith(d + os.sep)


def in_memory(base, target):
    """target(绝对路径)是不是 base 所在项目记忆目录本层或下一层子目录里的 .md。guard 放行子代理写记忆、dream mv / rm 共用这一个判断。
    记忆目录必须在配置目录的 projects/ 下:项目设置能把 autoMemoryDirectory 指到任意位置(比如 ~),不能因此放行改 ~/.claude/CLAUDE.md;
    target 整个取 realpath:符号链接也不能指到外面。"""
    mem = status.memory_location(base)["dir"]
    if not mem:
        return False
    real_mem = os.path.normcase(os.path.realpath(mem))
    if not real_mem.startswith(os.path.normcase(os.path.realpath(os.path.join(status.claude_dir(), "projects"))) + os.sep):
        return False
    real = os.path.normcase(os.path.realpath(target))
    if not real.startswith(real_mem + os.sep):
        return False
    rel = real[len(real_mem) + 1:].replace(os.sep, "/")
    return rel.endswith(".md") and rel.count("/") <= 1


def _mem_base(mem):
    """begin:存底。不是仓库就 init 并关掉 autocrlf;在别的仓库里面就不提交。"""
    if _run(mem, "rev-parse", "--show-toplevel")[0]:
        _must(mem, "init", "-q")
        _must(mem, "config", "core.autocrlf", "false")
    if _mem_own_repo(mem):
        _mem_commit(mem, t("DR_PRE"))


# ---------------------------------------------------------------- begin / git-log / abort

def _plan_findings(wt):
    """worktree 里跑一次 check,取方案类(PL-DUP / PL-STALE / PLN2)的发现;check 没跑起来(退出 2)就没有。"""
    p = subprocess.run([sys.executable, NOMESS, "check", "--json", "--all", "--no-exec"], cwd=wt, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode not in (0, 1):
        return []
    return ["%s %s: %s" % (f["rule"], f["file"], f["msg"]) for f in json.loads(p.stdout) if f["rule"] in ("PL-DUP", "PL-STALE", "PLN2")]


def begin(root):
    if not _acquire(root):
        print(t("DR_BUSY"))
        return 3
    try:
        _remove_wt(root)
        wt = _wt(root)
        _must(root, "worktree", "add", "--detach", wt, "HEAD")
        mem = status.memory_location(root)["dir"]
        if mem and _run(mem, "rev-parse", "--show-toplevel")[0] and not _under_claude(mem):
            mem = ""  # 项目级 settings 可指到任意位置:不在配置目录下又不是仓库,不替它 git init、不碰
        if mem:
            _mem_base(mem)
        with snapshot.open_snapshot(root, "tree", "HEAD") as snap:
            cfg = nm_config.load_snapshot(snap)
            exp = nm_config.expanded(cfg)
            items, _ = scan(root, snap, cfg, exp, _state(root))
            no_alias = sum(1 for e in lessons.snapshot_entries(snap, exp["lessons_dir"]) if not e["aliases"])
        items["plans"] = _plan_findings(wt)
        rows = [(k, line) for k, lines in items.items() for line in lines]
        cap = exp["dream"]["max_items"]
        shown, more = rows[:cap], len(rows) - cap
        nm_config.atomic_write(os.path.join(_common(root), LOCK), json.dumps({"backlog": more > 0, "notes0": _count_notes(root), "wt": wt}))
    except BaseException:
        _remove_wt(root)
        _release(root)
        raise
    if _state(root)["no_net_delete"]:
        print(t("DR_NO_NET"))
    print(t("DR_LIST", len(shown)))
    for k in dict.fromkeys(k for k, _ in shown):
        print("[%s]" % t("DR_K_" + k))
        for _, line in (r for r in shown if r[0] == k):
            print("  " + line)
    if more > 0:
        print(t("DR_MORE", more))
    if no_alias:
        print(t("DR_ALIAS", no_alias))
    print(t("DR_WT", wt))
    print(t("DR_MEM", mem) if mem else t("DR_MEM_NONE"))
    print(t("DR_NOTES_AT", os.path.join(wt, NOTES)))
    return 0


def git_log(root, word):
    """给整理的 AI 核实事实用:只调本插件的命令,权限钩子才能免弹窗放行。"""
    cwd = wt_path(root) if os.path.isdir(wt_path(root)) else root
    print(_must(cwd, "log", "-S" + word, "--oneline", "-n", "20"))
    return 0


def _head_view(root):
    """落地或放弃之后的 HEAD:(指纹, 还在文档根里没归类的页数)。"""
    with snapshot.open_snapshot(root, "tree", "HEAD") as snap:
        exp = nm_config.expanded(nm_config.load_snapshot(snap))
        return _fingerprint(root, exp, snap), len(doctypes.misplaced(snap, exp))


def abort(root):
    if not os.path.isfile(os.path.join(_common(root), LOCK)):
        print(t("DR_NOBEGIN"))
        return 0
    try:
        _remove_wt(root, (_lock_data(root) or {}).get("wt"))
        st = _state(root)
        st.update(last_attempt=_today(), fingerprint=_head_view(root)[0], backlog=False)
        _save(root, st)
    finally:
        _release(root)
    return 0


# ---------------------------------------------------------------- land

def _tail(text):
    return " ".join(text.split())[-300:]


def _nomess(wt, *args):
    return subprocess.run([sys.executable, NOMESS, *args], cwd=wt, capture_output=True, text=True, encoding="utf-8", errors="replace")


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git 的空树:记忆仓库 unborn HEAD(begin 时目录为空没有存底提交)时当基准


def _base(cwd):
    return "HEAD" if _run(cwd, "rev-parse", "-q", "--verify", "HEAD")[0] == 0 else EMPTY_TREE


def _changes(wt):
    """worktree 全部暂存后相对 HEAD 的改动 [(状态字母, 路径...)](R 带旧、新两个路径;相似度 30% 以上算改名,整理常顺手改链接)。"""
    tok = [x for x in _must(wt, "diff", "--cached", "-z", "--name-status", "-M30%", _base(wt)).split("\0") if x]
    out, i = [], 0
    while i < len(tok):
        n = 3 if tok[i][0] in "RC" else 2
        out.append((tok[i][0], *tok[i + 1:i + n]))
        i += n
    return out


def writable(p, exp, site):
    """整理时 AI(和落地护栏)认可改动的路径(posix 相对路径):文档根和教训目录下的 .md、开发者文档、AGENTS.md、.nomess/dream-notes.md;
    对外文档一律不在内(13.13:脚本保证绝不自动改)。开发者文档只许修改,新增 / 删除 / 改名由 _vet 和 may_edit 另外挡。
    land 护栏和 guard 的 Edit/Write 放行共用这一个函数。nomess.json 和基线即使落在这些目录里也不许。site 是 doctypes.site_dir 认出的网站源目录。"""
    if p in ("AGENTS.md", NOTES.replace(os.sep, "/")):
        return True
    tier = doctypes.tier_of(exp, site)(p)
    if tier or p in (nm_config.CONFIG_NAME, exp["check"]["baseline"]) or not p.endswith(".md"):
        return tier == "dev" and p.endswith(".md")
    return p.startswith((exp["docs_root"] + "/", exp["lessons_dir"] + "/"))


def may_edit(base, target):
    """guard 用:target(绝对路径)是不是整理 worktree 里 writable 认可的文件。目录部分取 realpath,防符号链接指到外面、防改写 .git。
    规则对着 worktree 的 HEAD(begin 时的提交)里的配置,不读 worktree 里可能被改过的 nomess.json。"""
    wt = wt_path(base)
    if not os.path.isdir(wt):
        return False
    real_wt = os.path.realpath(wt)
    real = os.path.realpath(target)  # 整个 target 取 realpath:被跟踪的符号链接也不能指到外面
    if not os.path.normcase(real).startswith(os.path.normcase(real_wt) + os.sep):  # 前缀比较不分大小写(Windows)
        return False
    rel = real[len(real_wt) + 1:].replace(os.sep, "/")  # 截出的 rel 保留磁盘上的大小写:public / dev 的 glob 区分大小写
    with snapshot.open_snapshot(wt, "tree", "HEAD") as snap:
        exp = nm_config.expanded(nm_config.load_snapshot(snap))
        site = doctypes.site_dir(snap)
        if doctypes.tier_of(exp, site)(rel) == "dev" and not snap.isfile(rel):  # 开发者文档只许改已有的,不许新建
            return False
    return writable(rel, exp, site)


def _in_scope(p, exp, site):
    """删除、改名源端的范围:文档根和教训目录下也只许 .md,并含 refresh 生成的规则文件目录;开发者文档和对外文档不在内(不许删、不许挪)。"""
    return p not in (nm_config.CONFIG_NAME, exp["check"]["baseline"]) and not doctypes.tier_of(exp, site)(p) and (
        p.startswith((".claude/rules/nomess/",)) or p == "AGENTS.md"
        or p.startswith((exp["docs_root"] + "/", exp["lessons_dir"] + "/")) and p.endswith(".md"))


def _allowed(p, exp, site):
    """新增、改名目标:writable 去掉开发者文档(只许修改),外加 refresh 生成的 .claude/rules/nomess/。"""
    return writable(p, exp, site) and doctypes.tier_of(exp, site)(p) != "dev" or (p.startswith(".claude/rules/nomess/") and _in_scope(p, exp, site))


def _vet(snap, wt, exp, changes):
    """护栏;不过返回原因,过了返回 None。"""
    sg, site = set(strays(snap, exp)), doctypes.site_dir(snap)
    for st, *ps in changes:
        old, new = ps[0], ps[-1]
        if st == "R":  # 13.10 的接管:散落 .md 改名进文档根才许删文档根外的被跟踪文件
            ok = _allowed(new, exp, site) and (_in_scope(old, exp, site) or old in sg)
        elif st == "D":
            ok = _in_scope(old, exp, site) and old != "AGENTS.md"
        else:
            ok = st == "A" and _allowed(new, exp, site) and new != "AGENTS.md" or st == "M" and (writable(new, exp, site) or _allowed(new, exp, site))
        if not ok:
            return t("DR_FORBID", " -> ".join(ps))
    if any(st == "M" and ps[0] == "AGENTS.md" for st, *ps in changes):
        with open(os.path.join(wt, "AGENTS.md"), encoding="utf-8") as f:
            crlf = lambda x: x.replace("\r\n", "\n")
            if GEN_BLOCK.sub("", crlf(f.read())) != GEN_BLOCK.sub("", crlf(snap.text("AGENTS.md"))):
                return t("DR_AGENTS")
    with snapshot.open_snapshot(wt, "index") as new:
        now = {lessons.title_key(e["title"]): e for e in lessons.snapshot_entries(new, exp["lessons_dir"])}
    old = {lessons.title_key(e["title"]): e for e in lessons.snapshot_entries(snap, exp["lessons_dir"])}
    for k, e in old.items():
        n = now.get(k)
        if lessons.is_external(e) and n and (n["verified"] or not lessons.is_external(n)):
            return t("DR_EXTERNAL", e["title"])
    if any(lessons.is_external(e) and k not in now for k, e in old.items()):  # 改了标题就逃过上面的检查:这时新增的条目一律不许是已核实
        for k, n in now.items():
            if k not in old and n["verified"]:
                return t("DR_NOVERIFY", n["title"])
    p = _nomess(wt, "check", "--no-exec")
    if p.returncode:
        return t("DR_CHECK", _tail(p.stdout + p.stderr))
    return None


def _loss(cwd, gen):
    """cwd 里暂存后相对 HEAD 的损失,从 numstat 算:{net 净删行数, deleted 被删的页, shrunk [(页, 净减行数)] 从多到少}。
    net 不计:新路径含 /archive/ 的(归档只是挪)、gen 前缀下的生成物、二进制;deleted 只去掉生成物(归档里删的页也该说)。
    改名只看内容变化(-M30%,和 _changes 同一个阈值),所以合并(一份删、一份加)净删小。"""
    deleted = [ps[0] for st, *ps in _changes(cwd) if st == "D" and not ps[0].startswith(gen)]
    tok = _must(cwd, "diff", "--cached", "--numstat", "-z", "-M30%", _base(cwd)).split("\0")
    net, shrunk, i = 0, [], 0
    while i < len(tok) and tok[i]:
        a, d, path = tok[i].split("\t", 2)
        i += 1
        if not path:  # 改名:后面跟旧、新两个路径
            path, i = tok[i + 1], i + 2
        if a == "-" or "/archive/" in path or path.startswith(gen):
            continue
        n = int(d) - int(a)
        net += n
        if n > 0 and path not in deleted:
            shrunk.append((path, n))
    return {"net": net, "deleted": deleted, "shrunk": sorted(shrunk, key=lambda x: -x[1])}


def _gone(*losses):
    """被删的页和缩得最多的页(各最多 LIST_MAX 个,超出写“等 N 个”)-> [文字片段];记忆侧的名字前加 memory/。"""
    def cut(names):
        return ", ".join(names[:LIST_MAX]) + (t("DR_ETC", len(names) - LIST_MAX) if len(names) > LIST_MAX else "")
    dels = [n for L in losses for n in L["deleted"]]
    shr = sorted((x for L in losses for x in L["shrunk"]), key=lambda x: -x[1])
    return ([t("DR_GONE", cut(dels))] if dels else []) + ([t("DR_SHRUNK", cut(["%s -%d" % x for x in shr]))] if shr else [])


def _counts(changes, exp):
    """(挪, 合并或删, 归档, 改写):从 diff 推,不让 AI 自报;自动生成的文件(系统图、规则文件、AGENTS.md)不算改写。"""
    gen = nm_map.out_dir(exp) + "/"
    moved = removed = archived = rewritten = 0
    for st, *ps in changes:
        new = ps[-1]
        if "/archive/" in new and st in "RA":
            archived += 1
        elif st == "R":
            moved += 1
        elif st == "D":
            removed += 1
        elif st == "M" and not new.startswith((gen, ".claude/rules/nomess/")) and new != "AGENTS.md":
            rewritten += 1
    return moved, removed, archived, rewritten


def _pick(root, wt, sha):
    """回到主检出 cherry-pick 这一个提交。先由脚本查:没有已暂存内容、这次提交碰到的文件没有未提交改动。
    不满足或冲突:abort、放弃;不重试、不解决冲突。返回 (新提交号, 原因)。"""
    if _run(root, "symbolic-ref", "-q", "HEAD")[0]:
        return None, t("DR_GITOP", "detached HEAD")
    for x in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "BISECT_LOG"):
        if os.path.exists(_must(root, "rev-parse", "--path-format=absolute", "--git-path", x)):
            return None, t("DR_GITOP", x)
    if _run(root, "diff", "--cached", "--quiet")[0]:
        return None, t("DR_STAGED")
    touched = {x for x in _must(wt, "diff-tree", "-r", "--no-commit-id", "--name-only", "--no-renames", "-z", sha).split("\0") if x}
    tok = [x for x in _must(root, "status", "--porcelain", "-z", "--untracked-files=all").split("\0") if x]
    dirty, i = set(), 0
    while i < len(tok):  # 每条 "XY 路径",改名后面多跟一个旧路径
        dirty.add(tok[i][3:])
        i += 2 if tok[i][0] in "RC" else 1
    if dirty & touched:
        return None, t("DR_DIRTY", ", ".join(sorted(dirty & touched)[:5]))
    rc, out, err = _run(root, "cherry-pick", sha, ident=True)
    if rc:
        if _run(root, "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD")[0] == 0:  # 开始前已确认不存在,所以这个是我们自己的
            _must(root, "cherry-pick", "--abort")
        return None, t("DR_PICK", _tail(err or out))
    return _must(root, "rev-parse", "HEAD"), None


def land(root):
    lp = os.path.join(_common(root), LOCK)
    if not os.path.isfile(lp):
        print(t("DR_NOBEGIN"))
        return 2
    lock = _lock_data(root)
    if lock is None:  # 锁内容读不出:按死锁处理,清掉
        _remove_wt(root)
        _release(root)
        print(t("DR_NOBEGIN"))
        return 2
    wt = lock.get("wt") or wt_path(root)
    if not os.path.isdir(wt):
        print(t("DR_NOBEGIN"))
        return 2
    st = _state(root)
    st.update(last_attempt=_today(), backlog=False)  # 中途出异常也记一次尝试
    head = nochange = None
    summary = None
    try:
        try:
            with snapshot.open_snapshot(wt, "tree", "HEAD") as snap:  # begin 时的 HEAD:护栏对着它比
                exp = nm_config.expanded(nm_config.load_snapshot(snap))
                # 先暂存、算项目侧净删(这时 worktree 里只有 AI 的改动),再跑 refresh:refresh 重写的生成段不算 AI 的删改
                _must(wt, "add", "-A")
                none = {"net": 0, "deleted": [], "shrunk": []}
                loss = _loss(wt, (nm_map.out_dir(exp) + "/", ".claude/rules/nomess/", "AGENTS.md"))
                # refresh 会执行 nomess.json 里的 cmd 生成器:worktree 里这个文件被改过(已暂存或未暂存)就不跑,整个丢弃
                if _run(wt, "diff", "--quiet", "HEAD", "--", nm_config.CONFIG_NAME)[0]:
                    reason = t("DR_FORBID", nm_config.CONFIG_NAME)
                else:
                    p = _nomess(wt, "refresh")
                    reason = t("DR_REFRESH", _tail(p.stdout + p.stderr)) if p.returncode else None
                if reason is None:
                    _must(wt, "add", "-A")
                    changes = _changes(wt)
                    nochange = not changes
                    reason = None if nochange else _vet(snap, wt, exp, changes)
            # 记忆侧先提交(与项目侧成败无关),因为防大删要把两侧的净删加起来判;超线时下面再 revert 它
            mem = status.memory_location(root)["dir"]
            mem_c = mem_err = None
            mem_loss = none
            mem_skip = bool(mem) and not _mem_own_repo(mem)
            if mem and not mem_skip:
                try:
                    _must(mem, "add", "-A", "--", ".")
                    mem_loss = _loss(mem, ())
                    mem_loss["deleted"] = ["memory/" + x for x in mem_loss["deleted"]]
                    mem_loss["shrunk"] = [("memory/" + x, n) for x, n in mem_loss["shrunk"]]
                    mem_c = _mem_commit(mem, t("DR_MEM_MSG"))
                except DreamError as e:
                    mem_err = _tail(str(e))
            net_total = mem_loss["net"] + loss["net"]
            net_over = mem_reverted = False
            if net_total > NET_DELETE_MAX:  # 不管项目侧为什么已被丢弃都判:记忆侧大删不能因此漏过
                net_over = True
                names = t("DR_SEP").join(_gone(loss, mem_loss))
                reason = reason or t("DR_NET", net_total, NET_DELETE_MAX, names)
                st["no_net_delete"] = True
                if mem_c:
                    try:
                        _must(mem, "revert", "--no-edit", mem_c, ident=True)
                        mem_reverted = True
                    except DreamError as e:
                        mem_err = _tail(str(e))
            elif reason is None and not nochange:
                n = _counts(changes, exp)
                rc, out, err = _run(wt, "commit", "-q", "-m", t("DR_MSG", *n), ident=True)  # 走 pre-commit 钩子
                reason = t("DR_COMMIT", _tail(err or out)) if rc else None
                if reason is None:
                    head, reason = _pick(root, wt, _must(wt, "rev-parse", "HEAD"))
            src = os.path.join(wt, NOTES)
            if os.path.isfile(src):
                with open(src, encoding="utf-8") as f, open(os.path.join(root, NOTES), "a", encoding="utf-8", newline="\n") as g:
                    g.write(f.read().rstrip("\n") + "\n")
            if net_over:  # 并入 AI 自己的 notes 之后再写,编号才不会撞
                num = _count_notes(root) + 1
                with open(os.path.join(root, NOTES), "a", encoding="utf-8", newline="\n") as g:
                    g.write(t("DR_NET_NOTE", num, net_total, names, num) + "\n")
            notes = _count_notes(root) - lock["notes0"]
        finally:
            try:
                _remove_wt(root, wt)
            except OSError as e:
                print(t("DR_RM_WT", wt, e), file=sys.stderr)
        fp, unsorted = _head_view(root)
        ok = head is not None
        if ok:
            first = not st["landed_once"]
            args = (n[0], n[1], n[2], unsorted if first else n[3], head[:10], t("DR_SUM_MEM", mem, mem_c[:10]) if mem_c else "")
            parts = _gone(loss, mem_loss) + [t("DR_SHOW", head[:10])]
            summary = t("DR_SUM_FIRST" if first else "DR_SUM", *args) + "".join(t("DR_SEP") + x for x in parts) + (t("DR_SUM_NOTES", notes) if notes > 0 else "")
            st["no_net_delete"] = False
        elif net_over:  # 超线丢弃:总结要留给用户(下个会话开头会取出)
            summary = t("DR_DISCARD", reason) + (t("DR_NET_MEM") if mem_reverted else "") + (t("DR_SUM_NOTES", notes) if notes > 0 else "")
        elif mem_c:
            summary = t("DR_SUM_ONLY_MEM", reason or t("DR_NOCHANGE"), mem, mem_c[:10])
        if mem_skip:
            summary = (summary + ";" if summary else "") + t("DR_MEM_SKIP")
        if mem_err:
            summary = (summary + ";" if summary else "") + t("DR_MEM_FAIL", mem_err)
        backlog = ok and lock["backlog"]  # 有旧账接着整理;放弃时不留,免得天天重试同一个失败
        st.update(fingerprint="" if backlog else fp, backlog=backlog, landed_once=st["landed_once"] or ok, summary=summary or st["summary"])
    finally:
        _save(root, st)
        _release(root)
    print(summary or (t("DR_NOCHANGE") if nochange else t("DR_DISCARD", reason)))
    return 0


def _rel(wt, p):
    """命令行路径(相对 worktree,或 worktree 内的绝对路径)转成 posix 相对路径;跑到 worktree 外或含 .. 返回 None。"""
    rel = posixpath.normpath(os.path.relpath(os.path.join(wt, p), wt).replace(os.sep, "/"))
    return None if rel == ".." or rel.startswith("../") or rel == "." else rel


def _mem_move(root, src, dst):
    """记忆目录里的 mv / rm:直接动文件,不跑 git(记忆目录可能刚 init、也可能没有存底);land 时 _mem_commit 的 add -A 会一并记下。
    两端都要是 in_memory 认可的路径;目标已存在就拒绝(和 git mv 一样不覆盖)。"""
    s = os.path.abspath(src)
    if dst is None:
        os.remove(s)
        return 0
    d = os.path.abspath(dst)
    if not in_memory(root, d) or os.path.exists(d):
        print(t("DR_MV_REFUSED", dst), file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(d), exist_ok=True)
    os.rename(s, d)
    return 0


def move(root, src, dst):
    """mv(dst 为 None 时是 rm):整理 worktree 里 git mv / git rm,范围和 land 护栏同一套规则:源要 _in_scope 或是接管候选(strays),目标要 _allowed;
    源在项目记忆目录里(in_memory)时交给 _mem_move。"""
    wt = _wt(root)
    if not os.path.isdir(wt):
        print(t("DR_NOBEGIN"), file=sys.stderr)
        return 2
    if in_memory(root, os.path.abspath(src)):
        return _mem_move(root, src, dst)
    s, d = _rel(wt, src), dst and _rel(wt, dst)
    with snapshot.open_snapshot(wt, "tree", "HEAD") as snap:
        exp = nm_config.expanded(nm_config.load_snapshot(snap))
        site = doctypes.site_dir(snap)
        ok = s and (_in_scope(s, exp, site) or s in strays(snap, exp))  # 和 _vet 的改名源端一致:散落 .md 能挪进文档根(13.10 接管)
    if not ok:
        print(t("DR_MV_REFUSED", src), file=sys.stderr)
        return 2
    if dst is not None and (not d or not _allowed(d, exp, site)):
        print(t("DR_MV_REFUSED", dst), file=sys.stderr)
        return 2
    if d:
        os.makedirs(os.path.dirname(os.path.join(wt, d)), exist_ok=True)  # git mv 不建目标目录
    r = _run(wt, "mv", s, d) if dst is not None else _run(wt, "rm", "-q", s)
    if r[0]:
        print(t("DR_MV_REFUSED", _tail(r[2])), file=sys.stderr)
        return 2
    return 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess dream", description="auto tidy of lessons, docs and memory in a temporary worktree")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("begin", help="take the lock, make the worktree, print the work list")
    g = sub.add_parser("git-log", help="git log -S <word> --oneline -n 20, to verify facts")
    g.add_argument("word")
    sub.add_parser("land", help="guard, commit in the worktree, cherry-pick into the main checkout")
    sub.add_parser("abort", help="give up this run")
    sub.add_parser("mv", help="git mv inside the worktree, or move a file inside the memory directory").add_argument("paths", nargs=2)
    sub.add_parser("rm", help="git rm inside the worktree, or delete a file in the memory directory").add_argument("paths", nargs=1)
    a = ap.parse_args(argv)
    root = _root()
    if a.cmd in ("mv", "rm"):
        return move(root, a.paths[0], a.paths[1] if a.cmd == "mv" else None)
    return git_log(root, a.word) if a.cmd == "git-log" else {"begin": begin, "land": land, "abort": abort}[a.cmd](root)
