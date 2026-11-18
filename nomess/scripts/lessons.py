"""教训库(lessons_dir,缺省 <docs_root>/lessons/):*.md 里每条是 `## 标题` 加若干 `键: 值` 行(键见 messages.NAMES["lesson"],中英都认,写出按 lang);`内容:`(`What:`)可跨多行,到下一个键行或下一条为止。
代码围栏(``` 或 ~~~)里的行不当标题和键行。旧版写的 `日期:` 读作 `更新:`(覆盖时改写成 `更新:`)。
只有 `状态: 已核实`(`Status: verified`)算已核实;没写或写了不认识的都不算。
inbox.md 是待整理。add 的标题和库里已有条目相同(忽略大小写和空白)时原地覆盖那一条(旧说法靠 git 历史留着)。  find <关键词...>  add  status
"""
import datetime
import difflib
import os
import re

import nm_config
import pathglob
from messages import NAMES, alts, code_of, name as nm_name, t
from nm_config import F

INBOX = "inbox.md"
# 键代号(写出时按 NAMES 里的顺序,内容放最后:它可跨多行);读的时候中英键名都认
FIELDS = list(NAMES["lesson"])
_KEY_OF = dict({w: c for c in FIELDS for w in alts("lesson", c)}, **{"日期": "updated"})  # 日期:P4 之前的写法
FIELD_RE = re.compile(r"^(%s)[:：]\s?(.*)$" % "|".join(map(re.escape, _KEY_OF)))


def lessons_dir():
    config = nm_config.find_config()
    return os.path.join(os.path.dirname(config), nm_config.lessons_dir(nm_config.load(config)))


def text_lines(text):
    return text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")


def _lines(path):
    with open(path, encoding="utf-8-sig") as f:
        return text_lines(f.read())


def parse(path):
    """[{title, summary, status, updated, paths, rule, body, verified, file, line, keys}];line 是 `## ` 那行的行号(1 起),keys 是这条里出现过的键代号(含重复,按出现顺序)。"""
    return parse_lines(_lines(path), os.path.basename(path))


def parse_text(text, name):
    """同 parse,但直接给文本(从快照读的)。"""
    return parse_lines(text_lines(text), name)


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def in_fence(lines):
    """[bool]:每行是否是代码围栏行或在围栏里(围栏里的行不当结构)。"""
    out, fence = [], None
    for line in lines:
        m = FENCE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
            out.append(fence is not None)
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line.strip(" `~"):
                fence = None
            out.append(True)
    return out


def parse_lines(lines, file, head="## "):
    """同 parse,但直接给行;head 是条目标题行的前缀(系统页“坑”段里的条目用 `### `)。
    每条另带 end:这一条最后一行之后的行号(1 起,即下一条标题行或文件末尾 + 1)。"""
    out, e, field = [], None, None
    fenced = in_fence(lines)
    for i, line in enumerate(lines, 1):
        if not fenced[i - 1] and line.startswith(head):
            if e is not None:
                e["end"] = i
            e = dict.fromkeys(FIELDS, "")
            e.update(title=line[len(head):].strip(), file=file, line=i, keys=[])
            out.append(e)
            field = None
            continue
        if e is None:
            continue
        m = None if fenced[i - 1] else FIELD_RE.match(line)
        if m:
            field = _KEY_OF[m.group(1)]
            e["keys"].append(field)
            e[field] = m.group(2).strip()
        elif field == "body":
            e["body"] += "\n" + line
    if e is not None:
        e["end"] = len(lines) + 1
    for e in out:
        e["body"] = e["body"].strip()
        e["status"] = code_of("lesson_status", e["status"]) or e["status"]  # 中英写法归成代号 verified / unverified
        e["verified"] = e["status"] == "verified"
    return out


def all_entries(d):
    return [e for p in nm_config.glob_files(d, "*.md") for e in parse(p)]


def unverified_in(text):
    """一段文本里 `状态: 未核实`(`Status: unverified`)的行数。"""
    return len(re.findall(r"^(?:%s)[:：]\s*(?:%s)" % ("|".join(alts("lesson", "status")), "|".join(alts("lesson_status", "unverified"))),
                          text, re.M | re.I))


def count_unverified(d):
    """目录下所有 *.md 里未核实的行数(教训库和记忆页都用这个;读磁盘)。"""
    n = 0
    for p in nm_config.glob_files(d, "*.md"):
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            n += unverified_in(f.read())
    return n


def _norm(s):
    return s.lower().replace("\\", "/")


def title_key(t):
    return "".join(t.lower().split())


def is_external(e):
    """条目的 `来源:` 以 `外部` / `external` 开头 = 外部来源:永不进规则文件,也不该被自动整理转正(设计稿 13.2 F;L6 按同一写法判断)。"""
    return e["source"].lower().startswith(alts("source_kind", "external"))


def _file_context(kws):
    """kws 里第一个是仓库内已有文件的:(该文件的子系统, 它直接依赖的子系统们, {子系统: [文件]}, 仓库文件名集合);没有返回 None。
    子系统和依赖边取 arch.model()(走已有缓存),只取“它依赖谁”一层:改 A 要守的是 A 用到的东西的规矩,反向和多跳会把核心模块的教训带给所有人。"""
    import arch
    import deps
    import snapshot
    config = nm_config.find_config()
    root = os.path.dirname(config)
    rel = next((r for r in (os.path.relpath(os.path.abspath(k), root).replace("\\", "/") for k in kws) if os.path.isfile(os.path.join(root, r))), None)
    if rel is None:
        return None
    with snapshot.open_snapshot(root, "worktree") as snap:
        owner, _, sys_edges, _ = arch.model(snap, nm_config.expanded(nm_config.load(config)))
    by_system = {}  # 先按子系统分好文件:每条教训只在要比的子系统的文件里找,不必每次扫一遍全仓库的归属表
    for f, x in owner.items():
        by_system.setdefault(x, []).append(f)
    mine = owner.get(rel)
    if mine is None:
        return rel, None, [], by_system
    return rel, mine, sorted({b for a, b in sys_edges if a == mine}), by_system


def _matcher(e):
    """条目 `路径:` 的匹配函数;没写或写了不支持的 glob 返回 None(rules 会报 RUL5)。"""
    try:
        return pathglob.matcher(pathglob.split_globs(e["paths"])) if e["paths"] else None
    except ValueError:
        return None


def _in_system(e, match, system, by_system):
    """条目的 `路径:`(match 是它编好的匹配函数,可为 None)匹配到该子系统的某个文件,或条目文字里出现子系统名。"""
    if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(system), " ".join((e["title"], e["summary"], e["body"])), re.I):
        return True
    return bool(match) and any(match(f) for f in by_system.get(system, ()))


def find(d, kws, limit=3):
    """按分取前 limit 条;返回的条目多一个 marks(如 `[同模块]`、`[依赖 net]`)。
    标题和别名命中同权重;参数是仓库里的文件时再加:`路径:` 命中 +10,同子系统 +4,直接依赖的子系统 +2(三选一取高)。"""
    ctx = _file_context(kws)
    kws = [_norm(k) for k in kws]
    scored = []
    for e in all_entries(d):
        ti, s_, b, al = _norm(e["title"]), _norm(e["summary"]), _norm(e["body"]), _norm(e["aliases"])
        s = sum(3 * (ti.count(k) + al.count(k)) + 2 * s_.count(k) + min(b.count(k), 2) for k in kws)
        e["marks"] = []
        if ctx:
            rel, mine, dep_systems, by_system = ctx
            match = _matcher(e)  # 每条只编译一次
            if match and match(rel):
                s += 10
            elif mine is None:
                pass
            elif _in_system(e, match, mine, by_system):
                s += 4
                e["marks"].append(t("MARK_SAME"))
            else:
                dep = next((x for x in dep_systems if _in_system(e, match, x, by_system)), None)
                if dep:
                    s += 2
                    e["marks"].append(t("MARK_DEP", dep))
        if s:
            scored.append((-s, e))
    scored.sort(key=lambda x: x[0])
    return [e for _, e in scored[:limit]]


def render(e):
    val = lambda c: nm_name("lesson_status", e[c]) if c == "status" and e[c] in NAMES["lesson_status"] else e[c]
    return ["## " + e["title"]] + ["%s: %s" % (nm_name("lesson", c), val(c)) for c in FIELDS if e[c]]


def add(d, title, summary, body, verified=True, aliases="", source=""):
    """同标题覆盖库里已有的那条,否则追加进 inbox。返回一行说明。aliases / source 为空时覆盖会保留旧条目的值。"""
    hit = next((x for x in all_entries(d) if title_key(x["title"]) == title_key(title)), None)
    e = dict(hit or dict.fromkeys(FIELDS, ""), title=title, summary=summary, body=body,
             **{k: v for k, v in (("aliases", aliases), ("source", source)) if v},
             status="verified" if verified else "unverified", updated=datetime.date.today().isoformat())
    if hit:
        p = os.path.join(d, hit["file"])
        lines = _lines(p)
        start, end = hit["line"] - 1, hit["end"] - 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[start:end] = render(e)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        return t("OVERWRITTEN", hit["file"], hit["title"])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, INBOX)
    head = "" if os.path.isfile(p) else t("INBOX_HEAD") + "\n"
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "\n" + "\n".join(render(e)) + "\n")
    return t("ADDED", INBOX)


def snapshot_entries(snap, d):
    """快照里教训库目录 d(相对仓库根)下所有条目。"""
    return [e for p in snap.ls(d, ".md") for e in parse_text(snap.text(p), p.rsplit("/", 1)[-1])]


def near_pairs(titles, ratio):
    """[(i, j)],i < j,titles[i] 和 titles[j] 几乎相同(去大小写、空白和标点后相等,或 difflib 相似度到 ratio)。教训体检 L4 和记忆体检 M7 共用。"""
    norm = [re.sub(r"[\W_]+", "", x.lower()) for x in titles]
    return [(i, j) for i in range(len(norm)) for j in range(i + 1, len(norm))
            if norm[i] and norm[j] and (norm[i] == norm[j] or difflib.SequenceMatcher(None, norm[i], norm[j]).ratio() >= ratio)]


def red(entries, rel):
    """教训库的确定性红项(提交钩子也查):L5 inbox 条目结构坏了。entries 是 snapshot_entries 的结果,rel 是库目录相对项目根的写法。
    inbox.md 设了 merge=union:不同条目各自追加能自动保留,但同标题并发修改会拼出重复标题或交错字段(同一条里同一个键出现两次),由合并的人解决。"""
    out, seen = [], {}
    for e in entries:
        if e["file"] != INBOX:
            continue
        where = "%s/%s" % (rel, INBOX)
        for k in dict.fromkeys(k for k in e["keys"] if e["keys"].count(k) > 1):
            out.append(F("red", "L5", where, e["line"], e["title"] + "|" + k, t("L5_KEY", e["title"], nm_name("lesson", k))))
        first = seen.setdefault(title_key(e["title"]), e)
        if first is not e:
            out.append(F("red", "L5", where, e["line"], e["title"], t("L5_DUP", e["title"], first["line"])))
    return out


def health(entries, rel, ratio):
    """教训库的黄项:L4 标题几乎相同。"""
    out = []
    for i, j in near_pairs([e["title"] for e in entries], ratio):
        a, b = entries[i], entries[j]
        out.append(F("yellow", "L4", "%s/%s" % (rel, a["file"]), a["line"], a["title"] + "|" + b["title"],
                     t("L4", b["file"], b["title"])))
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="nomess lessons", description="lesson library (lessons_dir, default <docs_root>/lessons/): find | add | status")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="look up by keyword / path, at most 3: title - summary; unverified ones are marked")
    f.add_argument("keywords", nargs="+")
    a_ = sub.add_parser("add", help="append an entry to inbox.md; overwrite in place if an entry with the same title exists")
    a_.add_argument("title")
    a_.add_argument("-s", "--summary", required=True, help="when it applies (with file paths and keywords)")
    a_.add_argument("-b", "--body", required=True, help="what to do, why, source")
    a_.add_argument("-k", "--aliases", default="", help="other names for it, comma separated, Chinese and English (e.g. \"存档, save, persistence\")")
    a_.add_argument("--external", metavar="SOURCE", help="learned from a web page, someone else's doc or tool output (URL or file): always written as unverified")
    a_.add_argument("--unverified", action="store_true", help="inferred, not tested; default is verified")
    sub.add_parser("status", help="inbox count, age of the oldest entry in days, unverified count (sorting empties the inbox)")
    a = ap.parse_args(argv)
    d = lessons_dir()
    if a.cmd == "find":
        for e in find(d, a.keywords):
            print("%s%s — %s [%s]%s" % (e["title"], "" if e["verified"] else t("UNVERIFIED_MARK"), e["summary"], e["file"], "".join(e["marks"])))
    elif a.cmd == "add":
        source = "%s %s" % (nm_name("source_kind", "external"), a.external) if a.external else ""
        print(add(d, a.title, a.summary, a.body, not (a.unverified or a.external), a.aliases, source))
    else:
        p = os.path.join(d, INBOX)
        es = parse(p) if os.path.isfile(p) else []
        dates = [datetime.date.fromisoformat(e["updated"]) for e in es if e["updated"]]
        age = (datetime.date.today() - min(dates)).days if dates else 0
        un = count_unverified(d)
        print(t("INBOX_STATUS", len(es), age, t("INBOX_UNVER", un) if un else ""))
    return 0
