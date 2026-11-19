"""文档类型表(唯一的家)、三档文档(13.13)和这几件事:
  DOC4  项目文档根(docs_root,缺省 docs)下的 .md 不在任何类型的位置(含目录超过两层):本次新增的红,存量黄;提示带出路。各级规模都开。
  DOC5  孤儿页(黄):从 <docs_root>/overview.md 沿相对链接走不到的页,合成一条(条数 + 前 3 个);归档方案和生成目录(system-map)不算。
  DOC6  超长(黄)。DOC7  说明页可能过时(黄):改了子系统的源文件、它的说明页存在却没改。
  docs-index 生成段(builtin.py 登记):放 overview.md 末尾,按类型分组列出全部文档,再列“未归类”(DOC4 存量)、开发者文档、对外文档。
类型 = 设计稿第 5 节的 7 类(总览、系统说明页、教训库、总排期、方案、归属图;代理入口 AGENTS.md 不在文档根下所以不列)
加全自动的 system-map,再加 nomess.json 的 doc_types 登记的类型。内置位置都相对 docs_root。
builtin_doc_types:false 时(13.15)只认 doc_types 表(加永远在的教训库和系统图);条目的 role 说明它沿用哪项内置功能,role_path() 是唯一的取法。
doc_places:"free" 时 DOC4 不报、guard 不挡,入口段改成“优先放进”。
三档:项目文档(上面这些,全管)、开发者文档 dev_docs(只就地改)、对外文档 public_docs(只读);DOC4–7 只看项目文档。"""
import difflib
import posixpath
import re

import doccheck
import lessons
import messages
import pathglob
from messages import NAMES, alts, name as nm_name, t
from nm_config import F, docs_root, est_tokens

INDEX_TOKENS = 1500  # docs-index 超过它先把归档方案收成“N 份 + 最新 5 份”,还超就把有多页的类型各收成一行(详单进该类型目录的 README.md,13.14)
ARCHIVE_KEEP = 5
SENTENCE = 100  # 每页“开头第一句”最多这么多字符

M = {
    "DOC4": ("docs page is not in any document-type location", "docs 页不在任何文档类型的位置"),
    "DOC4_WHY": ("one fact has one home; stray pages pile up and nobody finds them", "一个事实一个家;散放的页会越积越多、没人找得到"),
    "DOC6": ("docs page is over its length budget", "docs 页超过长度预算"),
    "DOC6_WHY": ("a page too long to read gets skipped; split details into sub-pages in the same folder", "太长没人读;把细节拆成同一文件夹里的子页"),
    "DT_BIG": ("%s is about %d tokens, over the budget of %s (%d); split details into sub-pages in the same folder and keep a summary here",
               "%s 约 %d token,超过「%s」的预算 %d;把细节拆成同一文件夹里的子页,这页留概要"),
    "DOC5": ("docs page cannot be reached from the overview by links", "从总览沿链接走不到的 docs 页"),
    "DOC5_WHY": ("a page nobody links to is invisible to people and to agents", "没人链到的页,人和代理都看不见"),
    "DT_MISPLACED": ("%s is not in a document-type location; move it to %s, or register its directory under `doc_types` in nomess.json",
                     "%s 不在任何文档类型的位置;放进 %s,或在 nomess.json 的 `doc_types` 登记它的目录"),
    "DT_ORPHANS": ("%d docs pages cannot be reached from %s by links (first %d: %s)",
                   "有 %d 个 docs 页从 %s 沿链接走不到(前 %d 个:%s)"),
    "DT_NO_INDEX": ("; the overview has no docs-index section: run `nomess init --auto` to add it",
                    ";总览没有目录段:跑 `nomess init --auto` 补上"),
    "DT_overview": ("Overview", "总览"),
    "DT_systems": ("System pages", "系统说明页"),
    "DT_lessons": ("Lessons", "教训库"),
    "DT_schedule": ("Schedule", "总排期"),
    "DT_plans": ("Plans", "方案"),
    "DT_ownership": ("Ownership map", "归属图"),
    "DT_system-map": ("System map", "系统图"),
    "DT_WHAT_overview": ("intent, principles, features; the human front page", "意图、原理、功能;人的首页"),
    "DT_WHAT_systems": ("what each system is, why it exists, what it works with", "每个系统是什么、为什么要有、和谁配合"),
    "DT_WHAT_lessons": ("pitfalls and rules learned the hard way", "踩过的坑和定下的规矩"),
    "DT_WHAT_schedule": ("the single entry for work and progress", "唯一的施工入口和进度视图"),
    "DT_WHAT_plans": ("designs and decision records; finished ones move to archive/", "方案兼决策记录;做完的挪进 archive/"),
    "DT_WHAT_ownership": ("the one owner of each shared datum and timing", "共享数据和时点的唯一主人"),
    "DT_WHAT_system-map": ("generated code map; do not edit by hand", "生成的代码地图,不要手改"),
    "DT_UNSORTED": ("Unsorted", "未归类"),
    "DT_UNSORTED_WHAT": ("not in any type location: move them, or register a type under `doc_types`", "不在任何类型的位置:挪过去,或在 `doc_types` 登记新类型"),
    "DT_UNSORTED_FREE": ("not in any type location", "不在任何类型的位置"),
    "DT_TYPE_LINE": ("%s — %d pages, see [%s](%s)", "%s — %d 份,见 [%s](%s)"),
    "DT_LESSONS_LINE": ("[lessons index](%s) — %d entries", "[教训索引](%s) — %d 条"),
    "DT_LESSONS_COUNT": ("%d lesson entries", "%d 条教训"),
    "DT_STATUS": ("(status: %s)", "(状态:%s)"),
    "DT_SUPERSEDED": ("→ superseded by %s", "→ 被 %s 取代"),
    "DT_ARCHIVE": ("%d archived plans; latest %d:", "归档方案 %d 份;最新 %d 份:"),
    "DOC7": ("system page may be out of date", "系统说明页可能过时"),
    "DOC7_WHY": ("code changed but its description did not; a stale page misleads the next reader", "代码改了说明没改;过时的说明会误导下一个读的人"),
    "DT_STALE_PAGE": ("system %s: %d source files changed but %s did not; update it if what it says is no longer true",
                      "子系统 %s 改了 %d 个源文件,说明页 %s 没改;说法不对了就改"),
    "DT_DEV": ("Developer docs", "开发者文档"),
    "DT_DEV_WHAT": ("for contributors; edited in place only", "给参与开发的人;只就地改"),
    "DT_PUBLIC": ("Public docs", "对外文档"),
    "DT_PUBLIC_WHAT": ("for users; never changed automatically", "给用户;自动整理不改"),
    "DT_TIER_DIR": ("`%s`: %d pages", "`%s`:%d 页"),
    "DT_WHERE": ("- Docs go only here: %s; a new .md elsewhere under %s/ is blocked.",
                 "- 文档只放这些位置:%s;%s/ 下别处新建 .md 会被挡。"),
    "DT_WHERE_FREE": ("- Docs go preferably here: %s.", "- 文档优先放进这些位置:%s。"),
    "DT_WHERE_LESSONS": ("lessons via `nomess lessons add`", "教训用 `nomess lessons add`"),
    "DT_NOW": ("- Write docs as things are now: change old wording in place, never append \"update: ...\"; history lives in git.",
               "- 文档只写现在的样子:旧说法直接改掉,不追加“更新:…”;历史靠 git。"),
}
messages.add(M)
RULES = [{"id": "DOC4", "level": "red", "what": "DOC4", "why": "DOC4_WHY"},
         {"id": "DOC5", "level": "yellow", "what": "DOC5", "why": "DOC5_WHY"},
         {"id": "DOC6", "level": "yellow", "what": "DOC6", "why": "DOC6_WHY"},
         {"id": "DOC7", "level": "yellow", "what": "DOC7", "why": "DOC7_WHY"}]

# 内置类型:(代号, 单个文件, 目录, 目录是否含子目录),路径相对 docs_root;顺序就是目录里的分组顺序。教训库目录取自配置,由 types() 填。
_BUILTIN = [("overview", ["overview.md", "README.md"], [], False),  # 文档目录的 README.md 是常见首页写法,归总览组
            ("systems", [], ["systems"], False),
            ("lessons", [], [None], False),
            ("schedule", ["schedule.md"], [], False),
            ("plans", [], ["plans", "plans/archive"], False),
            ("ownership", ["ownership-map.md"], [], False),
            ("system-map", [], ["system-map"], True)]
ROLES = ("overview", "systems", "schedule", "plans", "ownership")  # doc_types 条目能沿用的内置功能(13.15);教训库和系统图永远在、不进表
_ALWAYS = ("lessons", "system-map")
# 开发者文档、对外文档的内置 glob(开头 / = 只认仓库根)。nomess.json 的 dev_docs / public_docs 是在它们之上追加、不是替换:
# 写了自己的列表也不会让 README 之类变得可改。两档都匹配时算对外(更严的那档)。
DEV_DOCS = ["/CONTRIBUTING*", "/HACKING*", "/DEVELOPMENT*"]
PUBLIC_DOCS = ["/README*", "/CHANGELOG*", "/LICENSE*", "/SECURITY*", "/CODE_OF_CONDUCT*"]
SITE_MARKERS = (("docs/conf.py", "docs"), ("doc/conf.py", "doc"), ("docs/.vitepress", "docs"), ("docs/_config.yml", "docs"))  # site_dir 用
# DOC6 软预算(token)的缺省值,唯一定义处;nomess.json 的 doc_budget 按类型代号(内置)或登记的类型名覆盖
BUDGETS = {"overview": 3000, "systems": 3000, "lessons": 3000, "schedule": 4000, "plans": 6000}


def types(exp):
    """展开后的配置 -> [{id, name, what, files, dirs, deep}]:内置在前,doc_types 登记的在后(按配置顺序)。
    builtin_doc_types:false 时登记的在前、只跟教训库和系统图;带 role 的条目 id 就是 role,目录段、DOC6 等按内置那类对待(plans 也认 <dir>/archive)。"""
    root, full = exp["docs_root"], exp["builtin_doc_types"]
    built = []
    for tid, files, dirs, deep in _BUILTIN:
        if full or tid in _ALWAYS:
            built.append({"id": tid, "name": t("DT_" + tid), "what": t("DT_WHAT_" + tid), "files": [root + "/" + f for f in files],
                          "budget": exp["doc_budget"].get(tid, BUDGETS.get(tid)) if full else BUDGETS.get(tid),  # false 时 doc_budget 只认条目名
                          "dirs": [exp["lessons_dir"] if d is None else root + "/" + d for d in dirs], "deep": deep})
    mine = []
    for x in exp["doc_types"]:
        role, d = x.get("role"), x.get("dir")
        mine.append({"id": role or "doc_types:" + x["name"], "name": x["name"], "what": x["what"], "files": [x["file"]] if "file" in x else [],
                     "dirs": [d, d + "/archive"] if role == "plans" else [d] if d else [], "deep": False,
                     "budget": exp["doc_budget"].get(x["name"], BUDGETS.get(role))})
    return built + mine if full else mine + built


def builtin_dirs(root, lessons_dir, full=True):
    """内置类型占用的目录(doc_types 的 dir / file 不许和它们重叠,nm_config 校验用);full 为假(builtin_doc_types:false)只剩教训库和系统图。"""
    return {root + "/" + d for tid, _, dirs, _ in _BUILTIN for d in dirs if d and (full or tid in _ALWAYS)} | {posixpath.normpath(lessons_dir)}


def builtin_files(root, full=True):
    """内置类型占用的单个文件:只拿来挡新写法的 file 条目(老的 dir 条目照 1.1.1 只和目录比)。"""
    return {root + "/" + f for _, files, _, _ in _BUILTIN for f in files} if full else set()


def role_path(cfg, role):
    """role(ROLES 之一)那项内置功能读的文件或目录(仓库相对),没有返回 None(那项功能静默不跑)。原始配置和 expanded() 后的都能传。
    builtin_doc_types 为真(缺省)时就是内置位置 <docs_root>/overview.md、/systems、/schedule.md、/plans、/ownership-map.md,
    和 1.1.1 写死的一字不差;为假时取 doc_types 里带这个 role 的条目。"""
    if cfg.get("builtin_doc_types", True):
        files, dirs = next((f, d) for tid, f, d, _ in _BUILTIN if tid == role)
        return docs_root(cfg) + "/" + (files or dirs)[0]
    x = next((x for x in cfg.get("doc_types", []) if x.get("role") == role), None)
    return x and (x.get("file") or x.get("dir"))


def overview(exp):
    return role_path(exp, "overview")


def site_dir(snap):
    """文档网站的源目录(仓库相对),认不出返回 None。init --auto 登记对外文档、tier_of 的兜底共用这一处。
    只认各工具的固定文件名,配置里的目录用一行正则取(不为它加 YAML / TOML 依赖):mkdocs.yml 的 docs_dir(缺省 docs)、
    docusaurus.config.*(docs/)、Sphinx 的 docs/conf.py 或 doc/conf.py、docs/.vitepress/、book.toml 的 src(缺省 src)、Jekyll 的 docs/_config.yml。"""
    for name, key, default in (("mkdocs.yml", "docs_dir", "docs"), ("book.toml", "src", "src")):
        text = snap.text(name)
        if text is not None:
            m = re.search(r"^%s\s*[:=]\s*['\"]?([^'\"#\s]+)" % key, text, re.M)  # 只认顶层键(行首无缩进)
            d = posixpath.normpath(m.group(1).replace("\\", "/")) if m else default
            return None if d == "." or d.startswith("/") or ".." in d.split("/") else d  # 指到根或仓库外:不认
    if any(f.startswith("docusaurus.config.") for f in snap.ls("")):
        return "docs"
    return next((d for marker, d in SITE_MARKERS if snap.isfile(marker) or snap.isdir(marker)), None)


def tier_of(exp, site=None):
    """-> 函数 路径 -> "public" | "dev" | None(项目文档,或根本不是文档)。
    site 是 site_dir() 认出的网站源目录:不在任何类型位置、落在它里面的页也算对外文档。这是给没写 public_docs 的老 mkdocs 等项目的兜底
    (升级后网站页不该被 DOC4–6 报、被 guard 挡、被整理改);nomess 自己类型位置上的页照常管。不参与 public_docs 的配置校验。"""
    pub = pathglob.matcher(PUBLIC_DOCS + exp["public_docs"])
    dev = pathglob.matcher(DEV_DOCS + exp["dev_docs"])
    tys = types(exp) if site else ()
    return lambda p: "public" if pub(p) else "dev" if dev(p) else (
        "public" if site and p.startswith(site + "/") and type_of(p, tys) is None else None)


def _belongs(rel, ty):
    if rel in ty["files"]:
        return True
    for d in ty["dirs"]:
        if rel.startswith(d + "/") and (ty["deep"] or "/" not in rel[len(d) + 1:]):
            return True
    return False


def type_of(rel, tys):
    """docs 页 -> 所属类型(dict),不在任何类型的位置返回 None。"""
    return next((ty for ty in tys if _belongs(rel, ty)), None)


def is_type_index(rel, ty, snap):
    """rel 是不是类型 ty 的索引页(<首个目录>/README.md 且含 type-index 生成段标记):不算该类型的页,DOC5、DOC6 和目录都不把它当页。
    只认路径会把项目原有的手写 README 吞掉(从目录消失、DOC5/6 不查),所以还要看标记。
    pages() 仍含它:DOC5 的可达判断要顺着它的链接走(收起后类型下的页只在它里面列着)。"""
    if not (ty and ty["dirs"] and rel == ty["dirs"][0] + "/README.md"):
        return False
    import docgen
    return re.search("^" + re.escape(docgen.markers("type-index")[0]), snap.text(rel) or "", re.M) is not None


def pages(snap, exp):
    """项目文档:docs_root 下的 .md,去掉属于开发者文档、对外文档的。"""
    tier = tier_of(exp, site_dir(snap))
    return [p for p in snap.ls(exp["docs_root"], ".md", True) if not tier(p)]


def tier_pages(snap, exp, which):
    """仓库里属于开发者文档("dev")或对外文档("public")的 .md,排序。"""
    tier = tier_of(exp, site_dir(snap))
    return [p for p in snap.ls("", ".md", True) if tier(p) == which]


def misplaced(snap, exp):
    """项目文档里不在任何类型位置的 .md,排序。"""
    tys = types(exp)
    return [p for p in pages(snap, exp) if type_of(p, tys) is None]


def _suggest(rel, tys):
    """最像的类型位置:把这页的文件名放进每个候选位置(单文件类型就是那个文件,system-map 是生成的不推荐),取和原路径最像的。"""
    cand = [f for ty in tys if ty["id"] != "system-map" for f in ty["files"]]
    cand += [d + "/" + posixpath.basename(rel) for ty in tys if ty["id"] != "system-map" for d in ty["dirs"]]
    return difflib.get_close_matches(rel, cand, 1, 0)[0]


def blocked(rel, exp, snap):
    """guard 当场挡用(13.12 第 1 条):新建的 rel 是 docs_root 下、不属于开发者 / 对外文档、不在任何类型位置的 .md -> 提示语,否则 None。
    和 DOC4 新增报红是同一条规则,提前到动笔时省一轮返工。snap 只用来认网站源目录(site_dir),放在 docs_root 判断之后才读。"""
    if exp["doc_places"] == "free" or not (rel.startswith(exp["docs_root"] + "/") and rel.endswith(".md")) or tier_of(exp, site_dir(snap))(rel):
        return None
    tys = types(exp)
    return None if type_of(rel, tys) else t("DT_MISPLACED", rel, _suggest(rel, tys))


def doc4(snap, changes, exp):
    if exp["doc_places"] == "free":  # 13.15:不管位置,散放的页只进目录段的“未归类”
        return []
    tys = types(exp)
    return [F("red" if changes.get(p) == "A" else "yellow", "DOC4", p, 1, "misplaced", t("DT_MISPLACED", p, _suggest(p, tys)))
            for p in misplaced(snap, exp)]


# ---------------------------------------------------------------- DOC5

def links_of(snap, rel):
    """rel 这页里指向别的 docs 页的相对链接(规范化后的仓库路径)。复用 doccheck.dead_links 的解析:回调只记路径、一律说存在。"""
    seen = []
    doccheck.dead_links(snap.text(rel) or "", lambda p: seen.append(posixpath.normpath(posixpath.join(posixpath.dirname(rel), p))) or True)
    return seen


def reachable(snap, exp):
    """从总览出发沿链接走得到的页(含总览)。"""
    known = set(pages(snap, exp))
    ov = overview(exp)
    todo, seen = [ov], {ov}
    while todo:
        for q in links_of(snap, todo.pop()):
            if q in known and q not in seen:
                seen.add(q)
                todo.append(q)
    return seen


def _archive(exp):
    """归档方案的目录前缀(带结尾 /);没有 plans 那一类时是个不会匹配任何路径的串。"""
    return (role_path(exp, "plans") or "\0") + "/archive/"


def doc5(snap, exp):
    ov, root = overview(exp), exp["docs_root"]
    if not snap.isfile(ov):
        return []
    seen = reachable(snap, exp)
    tys = types(exp)
    orphans = [p for p in pages(snap, exp) if p not in seen and not p.startswith((_archive(exp), root + "/system-map/"))
               and not is_type_index(p, type_of(p, tys), snap)]
    if not orphans:
        return []
    msg = t("DT_ORPHANS", len(orphans), ov, min(3, len(orphans)), ", ".join(orphans[:3]))
    if not re.search(r"^<!-- GEN:docs-index BEGIN -->", snap.text(ov) or "", re.M):
        msg += t("DT_NO_INDEX")
    return [F("yellow", "DOC5", ov, 0, "orphans", msg, k=["orphans"])]


def doc6(snap, exp):
    """DOC6(黄):按类型的软预算。归档方案和各类型的索引页(README.md)不查。"""
    tys = types(exp)
    out = []
    for p in pages(snap, exp):
        ty = type_of(p, tys)
        if ty is None or ty["budget"] is None or p.startswith(_archive(exp)) or is_type_index(p, ty, snap):
            continue
        n = est_tokens(snap.text(p) or "")
        if n > ty["budget"]:
            out.append(F("yellow", "DOC6", p, 0, "big", t("DT_BIG", p, n, ty["name"], ty["budget"]), k=["big"]))
    return out


def doc7(snap, changes, exp):
    """DOC7(黄):本次改了某子系统的源文件,而 <systems 目录>/<名>.md 存在且不在改动里 -> 每个子系统一条;没有 systems 那一类不跑。
    只按真实改动判:全量检查(nomess check、配置变了的提交)的 changes 是整棵树都算 A,说明页自己也在里面,所以自然不报。"""
    import arch
    import deps
    sysdir = role_path(exp, "systems")
    if not sysdir:
        return []
    owner = arch.ownership(snap, exp)
    n = {}
    for p in deps.sources([p for p, st in changes.items() if st != "D"]):
        if owner.get(p):
            n[owner[p]] = n.get(owner[p], 0) + 1
    out = []
    for name, k in sorted(n.items()):
        page = "%s/%s.md" % (sysdir, name)
        if snap.isfile(page) and page not in changes:
            out.append(F("yellow", "DOC7", page, 0, "stale", t("DT_STALE_PAGE", name, k, page), k=["stale"]))
    return out


def run(snap, changes, eff):
    return doc4(snap, changes, eff.cfg) + doc5(snap, eff.cfg) + doc6(snap, eff.cfg) + doc7(snap, changes, eff.cfg)


# ---------------------------------------------------------------- 过时引用(整理清单用,13.12 第 4 条)

def stale_refs(snap, exp):
    """三档文档里反引号中的仓库路径(带 / 和扩展名;复用 plancheck.mentioned)在快照里已不存在 -> [(档, 页, 行号, 路径)]。
    档:project 直接改、dev 可就地改、public 只写 notes。不查:生成的系统图(refresh 会重写)、方案(含归档;历史记录,
    没归档的已有 PL-STALE)、教训库(条目讲的是当时的坑)。"""
    import plancheck
    tier = tier_of(exp, site_dir(snap))
    skip = (exp["docs_root"] + "/system-map/", (role_path(exp, "plans") or "\0") + "/", exp["lessons_dir"] + "/")
    out = []
    for rel in sorted(set(pages(snap, exp) + tier_pages(snap, exp, "dev") + tier_pages(snap, exp, "public"))):
        if rel.startswith(skip):
            continue
        seen = set()
        for n, p in plancheck.mentioned(snap.text(rel) or ""):
            if p not in seen and not snap.isfile(p) and not snap.isdir(p):
                seen.add(p)
                out.append((tier(rel) or "project", rel, n, p))
    return out


def where_lines(exp):
    """入口段“什么写在哪”(13.12 第 2 条),按类型表生成(含登记类型):一行位置、一行写法。"""
    parts = []
    for ty in types(exp):
        if ty["id"] == "system-map":  # 生成的,不让人写
            continue
        if ty["id"] == "lessons":
            parts.append(t("DT_WHERE_LESSONS"))
        elif ty["id"] == "systems":
            parts.append("%s `%s/<name>.md`" % (ty["name"], ty["dirs"][0]))
        else:
            parts.append("%s `%s`" % (ty["name"], (ty["files"] or [ty["dirs"][0] + "/"])[0]))
    if exp["doc_places"] == "free":  # 13.15:不挡,就不说“会被挡”
        return [t("DT_WHERE_FREE", " | ".join(parts)), t("DT_NOW")]
    return [t("DT_WHERE", " | ".join(parts), exp["docs_root"]), t("DT_NOW")]


# ---------------------------------------------------------------- docs-index 生成段

_SKIP = re.compile(r"^\s*(#|\||<!--|```|~~~|---|>|$)")


def _title(text, rel):
    m = re.search(r"^#[ \t]+(.+)$", text, re.M)
    return m.group(1).strip() if m else posixpath.splitext(posixpath.basename(rel))[0]


def _first_sentence(text):
    """标题之后第一段正文的第一句:跳过标题、表格、围栏、注释、方案头的键行;系统页的“这是什么:”去掉键名。"""
    keys = "|".join(map(re.escape, {w for c in NAMES["plan_head"] for w in alts("plan_head", c)}))
    what = "|".join(map(re.escape, alts("system_head", "what")))
    lines = lessons.text_lines(text)
    for line, fenced in zip(lines, lessons.in_fence(lines)):
        if fenced or _SKIP.match(line) or re.match(r"(%s)[:：]" % keys, line):
            continue
        line = re.sub(r"^(?:%s)[:：]\s*" % what, "", line.strip())
        line = re.sub(r"^[-*+]\s+", "", line)
        m = re.search(r"[。！？]|[.!?](?=\s|$)", line)
        s = line[:m.end()] if m else line
        return s if len(s) <= SENTENCE else s[:SENTENCE - 1] + "…"
    return ""


def _line(snap, rel, base, extra=""):
    text = snap.text(rel) or ""
    s = _first_sentence(text)
    return "- [%s](%s)%s%s" % (_title(text, rel), posixpath.relpath(rel, base), " — " + s if s else "", extra)


def _plan_line(snap, rel, base):
    h = doccheck.plan_head(snap.text(rel) or "")
    extra = ""
    if h.get("status"):
        st = h["status"]
        extra += " " + t("DT_STATUS", nm_name("plan_status", st) if st in NAMES["plan_status"] else st)
    if h.get("superseded_by"):
        extra += " " + t("DT_SUPERSEDED", h["superseded_by"])
    return _line(snap, rel, base, extra)


def _lessons_lines(snap, ty, base):
    d = ty["dirs"][0]
    ps = snap.ls(d, ".md")
    n = sum(len(lessons.parse_text(snap.text(p), posixpath.basename(p))) for p in ps if posixpath.basename(p) != "README.md")
    readme = d + "/README.md"
    return [t("DT_LESSONS_LINE", posixpath.relpath(readme, base), n) if snap.isfile(readme) else t("DT_LESSONS_COUNT", n)]


def _mine(snap, exp, ty, tys):
    return [p for p in pages(snap, exp) if type_of(p, tys) is ty and p != overview(exp) and not is_type_index(p, ty, snap)]


def _foldable(snap, exp, ty, tys):
    """能收成一行的类型:有目录、不是教训库(自己有 README)和系统图(本来就一行),且至少 2 页(不算它自己的索引页)。"""
    if not ty["dirs"] or ty["id"] in ("lessons", "system-map"):
        return False
    readme = ty["dirs"][0] + "/README.md"
    if snap.isfile(readme) and not is_type_index(readme, ty, snap):  # 手写的 README 没有生成段:清单没地方放,这一类型不收
        return False
    return len(_mine(snap, exp, ty, tys)) >= 2


def _group(snap, exp, ty, tys, base, collapse):
    if ty["id"] == "system-map":  # 系统图首页每次 refresh 都生成:固定链接,不看它此刻在不在(同一次 refresh 里它可能还没写出,看了就会自己把目录段判成过时)
        return ["- [%s](%s)" % (ty["name"], posixpath.relpath(ty["dirs"][0] + "/index.md", base))]
    mine = _mine(snap, exp, ty, tys)
    if not mine:
        return []
    if ty["id"] == "lessons":
        return _lessons_lines(snap, ty, base)
    if ty["id"] != "plans":
        return [_line(snap, p, base) for p in mine]
    archive = ty["dirs"][1] + "/"
    live = [p for p in mine if not p.startswith(archive)]
    old = sorted((p for p in mine if p.startswith(archive)), reverse=True)  # 文件名多以日期开头:倒序 = 最新在前
    out = [_plan_line(snap, p, base) for p in live]
    if collapse and len(old) > ARCHIVE_KEEP:
        out.append("- " + t("DT_ARCHIVE", len(old), ARCHIVE_KEEP))
        old = old[:ARCHIVE_KEEP]
    return out + [_plan_line(snap, p, base) for p in old]


def _render(snap, exp, base, level):
    """level 0 完整;1 归档方案收起;2 再把有多页的类型各收成一行。"""
    tys = types(exp)
    out = []
    for ty in tys:
        if level == 2 and _foldable(snap, exp, ty, tys):
            readme = ty["dirs"][0] + "/README.md"
            rel = posixpath.relpath(readme, base)
            lines = ["- " + t("DT_TYPE_LINE", ty["name"], len(_mine(snap, exp, ty, tys)), rel, rel)]
        else:
            lines = _group(snap, exp, ty, tys, base, level >= 1)
        if lines:
            out += ["### %s — %s" % (ty["name"], ty["what"]), ""] + lines + [""]
    stray = misplaced(snap, exp)
    if stray:
        out += ["### %s — %s" % (t("DT_UNSORTED"), t("DT_UNSORTED_FREE" if exp["doc_places"] == "free" else "DT_UNSORTED_WHAT")), ""] + [_line(snap, p, base) for p in stray] + [""]
    for which in ("dev", "public"):  # 13.13:这两档内容不归 nomess 管,只列出来让人能从首页找到
        lines = _tier_lines(snap, exp, which, base)
        if lines:
            key = "DT_" + which.upper()
            out += ["### %s — %s" % (t(key), t(key + "_WHAT")), ""] + lines + [""]
    return "\n".join(out).strip("\n")


def _tier_lines(snap, exp, which, base):
    """按 glob 收行:根目录的单文件 glob(/README* 之类)逐个列链接,其余(网站源 docs/** 之类)一个 glob 一行“前缀,N 页”,
    免得几百页的网站源把目录撑爆。每页只算进第一个匹配到的 glob。"""
    globs = (DEV_DOCS + exp["dev_docs"]) if which == "dev" else (PUBLIC_DOCS + exp["public_docs"])
    left = tier_pages(snap, exp, which)
    out = []
    for g in globs:
        rx = pathglob.matcher([g])
        mine = [p for p in left if rx(p)]
        left = [p for p in left if p not in mine]
        if not mine:
            continue
        if g.startswith("/") and "/" not in g[1:]:
            out += ["- [%s](%s)" % (p, posixpath.relpath(p, base)) for p in mine]
        else:
            out.append("- " + t("DT_TIER_DIR", re.split(r"[*?\[{]", g.lstrip("/"))[0] or g, len(mine)))
    return out


def _spec(cfg):
    return next((x for x in cfg.get("docgen", {}).values() if x.get("builtin") == "docs-index"), None)


def _levelled(snap, exp, base):
    """(docs-index 正文, 收到第几级):依次试完整、收起归档、按类型收,第一个不超 INDEX_TOKENS 的;都超就是第 2 级。"""
    for level in (0, 1):
        text = _render(snap, exp, base, level)
        if est_tokens(text) <= INDEX_TOKENS:
            return text, level
    return _render(snap, exp, base, 2), 2


def docs_index(snap, cfg, spec):
    """内置生成器 docs-index:全部 docs 页的目录。超过 INDEX_TOKENS 逐级收(见 _levelled)。同一棵树两次生成逐字节相同(只读快照、排序固定)。"""
    import nm_config
    return _levelled(snap, nm_config.expanded(cfg), posixpath.dirname(spec["file"]))[0]


def type_indexes(snap, cfg):
    """类型索引页的生成段(13.14):{相对路径: (类型名, 生成段正文)},正文就是该类型在完整目录里的那些行(归档方案收成“N 份 + 最新 5 份”)。
    已有的索引页(不论目录收没收起)都在内、照常刷新;不存在的只在 docs-index 收到按类型这一级、且该类型有多页时才算(由 docgen 新建)。"""
    import nm_config
    exp = nm_config.expanded(cfg)
    spec = _spec(cfg)
    base = posixpath.dirname(spec["file"])
    folded = _levelled(snap, exp, base)[1] == 2
    tys = types(exp)
    out = {}
    for ty in tys:
        if not ty["dirs"] or ty["id"] in ("lessons", "system-map"):
            continue
        readme = ty["dirs"][0] + "/README.md"
        if snap.isfile(readme) or folded and _foldable(snap, exp, ty, tys):
            out[readme] = (ty["name"], "\n".join(_group(snap, exp, ty, tys, ty["dirs"][0], True)))
    return out
