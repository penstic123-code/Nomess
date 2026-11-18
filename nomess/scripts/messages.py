"""脚本提示语和固定字段名的唯一出处。语言取自 nomess.json 的 lang(en / zh-CN,缺省 en),由 nm_config.load 设置。
  t(键, 参数...)  提示语,按 % 格式化;规则号(R1、GEN、DOC1 ...)不在表里,不随语言变。
  NAMES           固定字段名:中英都认(读),写出时按 lang。键名 -> (英文, 中文)。
"""
LANGS = ("en", "zh-CN")
_lang = "en"


def set_lang(lang):
    global _lang
    if lang not in LANGS:
        raise ValueError("lang must be one of: %s" % ", ".join(LANGS))
    _lang = lang


def lang():
    return _lang


def t(key, *args):
    s = M[key][LANGS.index(_lang)]
    return s % args if args else s


def add(table):
    """注册一个模块自己的提示语表 {键: (英文, 中文)}(模块顶层 M = {...}; messages.add(M))。先整表校验再一次合并:
    键已存在、或值不是两个字符串 -> ValueError,什么都不加。"""
    for k, v in table.items():
        if k in M:
            raise ValueError("duplicate message key %s" % k)
        if not (isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, str) for x in v)):
            raise ValueError("message %s must be (English, Chinese)" % k)
    M.update(table)


def name(group, code):
    """固定字段名 / 状态词在当前语言下的写法。group: NAMES 的键;code: 该组里的代号。"""
    return NAMES[group][code][LANGS.index(_lang)]


def alts(group, code):
    """读的时候认的所有写法(中英)。"""
    return NAMES[group][code]


def code_of(group, word):
    """文本里的写法(中英任一,忽略大小写)-> 代号;不认识返回 None。"""
    w = word.strip().lower()
    return next((c for c, ws in NAMES[group].items() if w in (x.lower() for x in ws)), None)


# 固定字段名:代号 -> (英文, 中文)。写出顺序 = 这里的顺序
NAMES = {
    "lesson": {"summary": ("When", "概述"), "status": ("Status", "状态"), "updated": ("Updated", "更新"),
               "paths": ("Paths", "路径"), "rule": ("Rule", "规则"),
               "aliases": ("Aliases", "别名"), "source": ("Source", "来源"), "body": ("What", "内容")},
    "source_kind": {"external": ("external", "外部")},  # `来源:` 的值以它开头 = 外部来源(lessons.is_external)
    "lesson_status": {"verified": ("verified", "已核实"), "unverified": ("unverified", "未核实")},
    "system_head": {"what": ("What", "这是什么"), "why": ("Why", "为什么要有"), "with": ("Works with", "和谁配合")},
    "plan_head": {"status": ("Status", "状态"), "supersedes": ("Supersedes", "取代"), "superseded_by": ("Superseded-by", "被取代"),
                  "systems": ("Systems", "系统")},
    "plan_status": {"proposed": ("proposed", "提案"), "accepted": ("accepted", "已采纳"), "rejected": ("rejected", "已否决"),
                    "superseded": ("superseded", "已被取代")},
    "sched_col": {"pkg": ("Package", "包"), "deps": ("Depends", "依赖"), "status": ("Status", "状态"),
                  "files": ("Files", "可改文件")},
    "sched_status": {"todo": ("Todo", "待派"), "doing": ("Doing", "在做"), "review": ("Review", "待审"), "rework": ("Rework", "返修中"), "merged": ("Merged", "已合")},
    "level": {"red": ("red", "红"), "yellow": ("yellow", "黄")},
}

M = {
    # nm_config
    "NO_CONFIG": ("no nomess.json found at or above %s (run init first)", "从 %s 往上没找到 nomess.json(先 init)"),
    "BAD_FORMAT": ("%s: format is not %s", "%s: format 不是 %s"),
    "NO_MAIN": ("%s: main_branch is missing (branch name, required)", "%s: 缺 main_branch(主分支名,必填)"),
    "BAD_LEVEL": ("%s: review.level must be one of %s", "%s: review.level 只能是 %s"),
    "BAD_SYSTEMS": ("%s: systems.%s must be a non-empty list of path globs", "%s: systems.%s 要是非空的路径 glob 列表"),
    "OUT_LINK": ("%s is a link or leads outside the generated directory; refusing to write (remove the link first)",
                 "%s 是链接或指到生成目录之外,拒绝写入(先去掉这个链接)"),
    "BAD_BUDGET": ("%s: %s.%s must be a positive integer (estimated token budget)", "%s: %s.%s 要是正整数(估算 token 预算)"),
    "BAD_PATH": ("%s: %s must be a relative path inside the repository (got %r)", "%s: %s 要是仓库内的相对路径(现在是 %r)"),
    # nomess.py
    "USAGE": ("usage: nomess %s [args]  (add -h to a subcommand for help)", "用法: nomess %s [参数]  (子命令加 -h 看说明)"),
    "TIMEOUT": ("command timed out (%ss): %s", "命令超时(%ss): %s"),
    "PY_OLD": ("Python 3.9+ required", "需要 Python 3.9+"),
    # check
    "RULE_MISSING": ("rule %s: missing %s", "规则 %s 缺 %s"),
    "RULE_LEVEL": ("rule %s: level must be red or yellow", "规则 %s: level 只能是 red / yellow"),
    "RULE_KIND": ("rule %s: exactly one of forbid / require / cmd", "规则 %s: forbid / require / cmd 三选一"),
    "RULE_GLOB": ("rule %s: a regex rule needs glob", "规则 %s: 正则规则要有 glob"),
    "RULE_WHY": ("prevents: %s", "防:%s"),
    "RULE_EXIT": ("exit code %d", "退出码 %d"),
    "GEN_STALE": ("generated section %s is stale, run nomess docgen", "生成段 %s 过时,跑 nomess docgen"),
    "MAP_STALE": ("system map %s is stale, run nomess map", "系统图 %s 过时,跑 nomess map"),
    "M1": ("no MEMORY.md / INDEX.md", "没有 MEMORY.md / INDEX.md"),
    "M4": ("directory nested too deep: only the index and topic pages are allowed, merge files up or move them into archive/",
           "目录超过两级:只许索引 + 主题页,子目录里的文件要并上来或进 archive/"),
    "M2": ("index is about %d tokens, over the budget of %d; merge topics when dreaming", "索引约 %d token,超预算 %d;做梦时合并主题"),
    "M3_BIG": ("topic page is about %d tokens, over the budget of %d; consider splitting when dreaming",
               "主题页约 %d token,超预算 %d;做梦时考虑拆分"),
    "M5_WIKI": ("dead link [[%s]]", "断链 [[%s]]"),
    "LINK_DEAD": ("dead link (%s)", "断链 (%s)"),
    "M6": ("%d memory items unverified, verify them against the code when dreaming", "%d 条记忆未核实,做梦时对着代码核实"),
    "M7": ("title nearly the same as %s (%s / %s), consider merging when dreaming", "和 %s 标题几乎相同(%s / %s),做梦时考虑合并"),
    "SUMMARY": ("nomess check: red %d yellow %d frozen %d%s", "nomess check: 红 %d 黄 %d 存量 %d%s"),
    "FROZEN_TAG": ("(frozen)", "(存量)"),
    "ALL_HINT": (" (--all to show everything)", "(--all 看全部)"),
    "RULES_LINE": ("%s %s checks: %s / prevents: %s", "%s %s 查:%s / 防:%s"),
    "FROZEN": ("baseline frozen: %d findings -> %s", "基线已冻结:%d 条 -> %s"),
    "BASELINE_OLD": ("baseline %s is not in the nomess-baseline/2 format; delete it and run nomess check --freeze again",
                     "基线 %s 不是 nomess-baseline/2 格式;删掉它再跑 nomess check --freeze"),
    "BASELINE_BAD": ("baseline %s: rule %s: %s", "基线 %s: 规则 %s: %s"),
    "BL1": ("the baseline has entries for rule %s, which is not known; remove them or register the rule",
            "基线里有规则 %s 的条目,但这个规则号不存在;删掉这些条目或登记这条规则"),
    "B1_KEY": ("baseline loosened: rule %s, %s (%s); fix the finding or add an allow with a reason",
               "基线被放宽:规则 %s,%s(%s);改掉违规,或加带理由的 allow"),
    "B1_FIRST": ("baseline loosened: rule %s was already enabled in the base, its findings cannot be frozen now (%s)",
                 "基线被放宽:规则 %s 在基准里已经启用,不能现在才冻结它的命中(%s)"),
    "B2_CFG": ("nomess.json loosened: %s (%s); only a person can approve this (loosening flow)", "nomess.json 被放宽:%s(%s);只能由人走放宽流程批准"),
    "B2_GONE": ("nomess.json exists in the base but not here; that turns the checks off (loosening)",
                "基准有 nomess.json、这里没有:等于关掉检查(放宽)"),
    "CFG1": ("unknown key %s in nomess.json%s", "nomess.json 里不认识的键 %s%s"),
    "CFG1_HINT": ("; did you mean %s?", ";是不是想写 %s?"),
    "CFG_BAD": ("%s: %s is invalid: %r", "%s: %s 不合法:%r"),
    "CFG_ID_DUP": ("rule id %s is used twice or is reserved (rule ids are global; built-in and diagnostic ids are reserved)",
                   "规则号 %s 重复或是保留号(规则号全局唯一,内置号和诊断号保留)"),
    "ALLOW_BAD": ("allow entry %s: %s", "allow 条目 %s: %s"),
    "SCOPE_TIE": ("scopes '%s' and '%s' are equally specific, both match %s and both set %s; make one more specific",
                  "scopes 的“%s”和“%s”一样具体,都命中 %s、都写了 %s;把其中一条写得更具体"),
    "CHK_SKIP": ("nomess: no nomess.json here or in the base, skipped", "nomess: 这里和基准都没有 nomess.json,跳过"),
    "CI_SAME": ("nomess: the base is the commit under check, nothing to compare", "nomess: 基准就是待检提交,没有可比的改动"),
    "CI_EXCLUSIVE": ("--ci cannot be combined with --freeze, --tighten, --rules, --no-exec or --memory",
                     "--ci 不能和 --freeze、--tighten、--rules、--no-exec、--memory 一起用"),
    "CI_DIRTY": ("--ci needs a clean checkout of HEAD (tracked files differ; cmd rules run in the working tree)",
                 "--ci 要求工作区和 HEAD 一致(已跟踪文件有改动;cmd 规则在工作区里跑)"),
    "CI_RENAME": ("baseline %s still names renamed paths; commit through the git hook (it rewrites them) or run nomess check --freeze",
                  "基线 %s 里还写着改名前的路径;经 git 钩子提交(它会改写),或手动跑 nomess check --freeze"),
    "CMD1": ("cmd rules %s skipped: tracked files have unstaged changes and cmd rules read the working tree; CI checks them",
             "cmd 规则 %s 没跑:已跟踪文件有未暂存改动,cmd 规则读的是工作区;交给 CI"),
    "GH_BASE_INDEX": ("nomess: baseline %s rewritten for renames in the index only (%s); the working tree copy is left as is",
                      "nomess: 基线 %s 按改名改写,只写进了索引(%s);工作区里的那份没动"),
    "CI_NEED_BASE": ("--ci needs --base <commit>", "--ci 要带 --base <提交>"),
    "TIGHTENED": ("baseline tightened -> %s", "基线已收紧 -> %s"),
    "RULES_OFF": (" (not enabled)", "(未启用)"),
    # doccheck
    "DOC3_HEAD": ("description page is missing head lines: %s:", "说明页开头缺三行头:%s:"),
    "HDR": ("file has no header comment (first line: what this file is for)", "文件缺头注释(第一行写这个文件是干什么的)"),
    "L1": ("%d lessons unverified, verify them against the code when dreaming", "%d 条教训未核实,做梦时对着代码核实"),
    "PLN1": ("plan header '%s' points to a missing file: %s", "方案头的“%s”指向不存在的文件:%s"),
    "PLN2_NONE": ("archived plan has no 'Status:' in its header", "归档方案缺方案头的“状态:”"),
    "PLN2_SUP": ("'Superseded-by' is set, so Status must be 'superseded'", "写了“被取代”,状态必须是“已被取代”"),
    "AGENTS1": ("AGENTS.md is about %d tokens, over the budget of %d; move details into path-scoped rules or docs",
                "AGENTS.md 约 %d token,超预算 %d;细节挪进按路径的规则或 docs"),
    "AGENTS2": ("CLAUDE.md does not import @AGENTS.md, so Claude Code will not read AGENTS.md",
                "CLAUDE.md 没有导入 @AGENTS.md,Claude Code 不会读 AGENTS.md"),
    "MAP1": ("system map index is about %d tokens, over the budget of %d; trim subsystem descriptions or raise map.index_tokens",
             "系统图首页约 %d token,超预算 %d;精简子系统说明或调大 map.index_tokens"),
    # lessons
    "L4": ("title nearly the same as %s#%s, consider merging when dreaming", "和 %s#%s 标题几乎相同,做梦时考虑合并"),
    "L5_KEY": ("inbox entry '%s' has the field '%s' twice (a union merge interleaved two edits): keep one", "inbox 条目 '%s' 里字段 '%s' 出现了两次(union 合并拼出了两份改动):只留一份"),
    "L5_DUP": ("inbox title '%s' is already used at line %d (same title after ignoring case and spaces): merge the two entries", "inbox 标题 '%s' 和第 %d 行重复(忽略大小写和空白后相同):合成一条"),
    "OVERWRITTEN": ("overwrote %s#%s", "已覆盖 %s#%s"),
    "ADDED": ("added to %s", "已加入 %s"),
    "INBOX_HEAD": ("# inbox (to be sorted, append only)", "# inbox(待整理,只追加)"),
    "UNVERIFIED_MARK": (" (unverified)", "(未核实)"),
    "MARK_SAME": (" [same module]", " [同模块]"),
    "MARK_DEP": (" [depends on %s]", " [依赖 %s]"),
    "INBOX_STATUS": ("inbox: %d items, oldest %d days ago%s", "inbox %d 条,最早 %d 天前%s"),
    "INBOX_UNVER": (", %d unverified", ",未核实 %d 条"),
    # rules
    "RULES_HEADER": ("<!-- generated by nomess rules, do not edit: write entries in lessons or the Pitfalls section of a system page, then run nomess rules -->",
                     "<!-- nomess rules 生成,不手改:条目写在教训或系统页“坑”段,改完跑 nomess rules -->"),
    "RUL1": ("rules file frontmatter is malformed, Claude would load it as an always-on rule: %s; run nomess rules to regenerate",
             "规则文件 frontmatter 写错,Claude 会把它当常驻规则:%s;跑 nomess rules 重新生成"),
    "FM_START": ("must start with ---, paths:, one or more `  - \"glob\"` lines, ---", "开头要是 ---、paths:、若干 `  - \"glob\"` 行、---"),
    "FM_LINE": ("lines under paths must be `  - \"glob\"`: %r", "paths 里的行要是 `  - \"glob\"`: %r"),
    "RUL2": ("rules file is stale, run nomess rules", "规则文件过时,跑 nomess rules"),
    "RUL3": ("rules file is about %d tokens, over the budget of %d; merge or move down when dreaming", "规则文件约 %d token,超预算 %d;做梦时合并或下沉"),
    "RUL4": ("rule %s: path %s matches no file (directory renamed or deleted?)", "规则 %s 的路径 %s 一个文件都匹不到(目录改名或删了?)"),
    "RUL5_HALF": ("entry %s needs both paths and rule to generate a rules file", "条目 %s 路径和规则要写全两个才生成规则文件"),
    "RUL5_LONG": ("rule of entry %s is too long (40 CJK characters / 25 words), put the detail in the entry",
                  "条目 %s 的规则太长(中文 40 字 / 英文 25 词内),细节放在条目里"),
    "RUL5_UNVERIFIED": ("entry %s has paths and rule but its status is not verified, so no rules file is generated (write Status: verified once checked)",
                        "条目 %s 写了路径和规则,但状态不是已核实,不生成规则文件(核实后写 状态: 已核实)"),
    "RUL5_GLOB": ("entry %s has a path glob nomess does not support (see pathglob.py), so no rules file is generated",
                  "条目 %s 的路径里有不支持的 glob(见 pathglob.py),不生成规则文件"),
    "STALE": ("stale", "过时"),
    "WRITTEN": ("written", "已写"),
    "REWRITTEN": ("rewritten", "已重写"),
    # docgen
    "GEN_MARKERS": ("%s: markers of generated section %s must be one per line, exactly one pair (%d BEGIN, %d END)",
                    "%s: 生成段 %s 的标记要各一行、恰好一对(BEGIN %d 个,END %d 个)"),
    "GEN_PY": ("generated section %s uses the removed py generator; use cmd instead, e.g. `python -c \"import x; print(x.f())\"` or a small script that prints the body",
               "生成段 %s 用了已删除的 py 生成器;改用 cmd,例如 `python -c \"import x; print(x.f())\"` 或一个打印正文的小脚本"),
    "GEN_SPEC": ("generated section %s needs file and exactly one of cmd / map / builtin",
                 "生成段 %s 要有 file,且 cmd / map / builtin 三选一"),
    "GEN_FAILED": ("generator %s exited with %d: %s", "生成器 %s 退出码 %d: %s"),
    "GEN_NO_OUT": ("no output", "无输出"),
    "GEN_NO_FILE": ("%s: host file of generated section %s not found (or not a regular file)", "%s: 生成段 %s 的宿主文件不存在(或不是普通文件)"),
    "GEN_UNKNOWN": ("nomess.json docgen has no %s (has: %s)", "nomess.json 的 docgen 里没有: %s(有: %s)"),
    # map
    "MAP_NO_TABLE": ("nomess.json map has no %s (has: %s)", "nomess.json 的 map 里没有 %s(有: %s)"),
    "MAP_HOTSPOT": ("map %s: hotspot needs by (one of the columns), max and label, and the table needs file_col",
                    "map %s: hotspot 要有 by(列名之一)、max、label,且表要开 file_col"),
    "MAP_GROUPS": ("map %s: regex has %d capture groups, %d columns listed", "map %s: 正则有 %d 个捕获组,列名有 %d 个"),
    "MAP_FILE_COL": ("File", "文件"),
    "MAP_ROWS": ("**%s** (%d rows)", "**%s**(%d 行)"),
    "MAP_MISSES": ("Misses: ", "会漏:"),
    "MAP_FILES": ("**Files** (%d; first sentence of the header comment, - means none)", "**文件清单**(%d 个;取头注释第一句,— 表示没有)"),
    "MAP_FILES_COLS": ("| File | Description |", "| 文件 | 说明 |"),
    "MAP_DEPS": ("**File dependencies** (%d; repo-internal only, regex-level, dynamic dependencies may be missed)",
                 "**文件依赖**(%d 条;只含仓库内部,正则级、可能漏动态依赖)"),
    "MAP_DEPS_COLS": ("| File | Depends on |", "| 文件 | 依赖 |"),
    "MAP_HOT_LINE": ("- %s: `%s` (%d files: %s; see [%s](%s.md))", "- %s:`%s`(%d 个文件:%s;见 [%s](%s.md))"),
    "MAP_HOT_DEPS": ("- depended on by too many: `%s` (%d files depend on it; see [file dependencies](deps.md))",
                     "- 被依赖过多:`%s`(%d 个文件依赖它;见 [文件依赖](deps.md))"),
    "MAP_SYS_NOPAGE": ("- **%s** — (no description page %s/systems/%s.md)", "- **%s** — (缺说明页 %s/systems/%s.md)"),
    "MAP_SYS_LINE": ("- **%s** — %s [page](../systems/%s.md)", "- **%s** — %s [说明页](../systems/%s.md)"),
    "MAP_SYS_NOWHAT": ("(description page has no 'What:')", "(说明页缺“这是什么”)"),
    "MAP_NAME_BAD": ("map table name %r cannot be a file name (no \\ / : * ? \" < > |, no leading/trailing dot or space, no device names)",
                     "map 表名 %r 不能当文件名(不许含 \\ / : * ? \" < > |、首尾的点和空格、设备名)"),
    "MAP_NAME_DUP": ("map table name %r clashes with a built-in page or another table (case-insensitive; built-in: %s)",
                     "map 表名 %r 与内置分页名或别的表重名(不分大小写;内置: %s)"),
    "MAP_IDX_TITLE": ("# System map (generated, do not edit)", "# 系统图(生成,不手改)"),
    "MAP_IDX_PAGES": ("## Pages", "## 分页"),
    "MAP_IDX_FILES": ("- [Files](files.md)", "- [文件清单](files.md)"),
    "MAP_IDX_DEPS": ("- [File dependencies](deps.md)", "- [文件依赖](deps.md)"),
    "MAP_IDX_HOT": ("## Overlaps and hotspots", "## 重叠和热点"),
    "MAP_IDX_NONE": ("none", "无"),
    "MAP_IDX_SYS": ("## Subsystems", "## 子系统"),
    "MAP_IDX_SYSDEPS": ("## Subsystem dependencies", "## 子系统依赖"),
    "MAP_IDX_REST": ("- %d more in the pages", "- 其余 %d 条见分页"),
    # builtin
    "LESSON_COUNT": ("- [%s](%s) — %d entries", "- [%s](%s) — %d 条"),
    "GEN_SKIP_BUILTIN": ("yellow: docgen section %s uses built-in generator %s, which no longer exists; skipped (remove it from nomess.json)", "黄:生成段 %s 用的内置生成器 %s 已不存在,已跳过(请从 nomess.json 删掉)"),
    "NO_BUILTIN": ("no built-in generator %s (has: %s)", "没有内置生成器 %s(有: %s)"),
    "ENTRY_1": ("- Design overview: `%s`; code map (system map index): `%s`.",
                "- 设计总览:`%s`;代码地图(系统图首页):`%s`。"),
    "ENTRY_1B": ("- Code map (system map index): `%s`.",
                 "- 代码地图(系统图首页):`%s`。"),
    "ENTRY_2": ("- `nomess check` runs automatically before commits; red findings block the commit, fix them as reported.",
                "- 提交前会自动跑 `nomess check`,有红项会挡下提交,照提示改。"),
    "ENTRY_3": ("- Before changing a directory, look up lessons: `nomess lessons find <path or keyword>`.",
                "- 改一个目录前先查教训:`nomess lessons find <路径或关键词>`。"),
    "ENTRY_4": ("- Start work by reading the top of `%s` (the single entry for work).",
                "- 开工先读 `%s` 开头(唯一施工入口)。"),
    # status / deps
    "STATUS_LINE": ("stale generated sections %d, memory over budget %d, inbox %d, memory dir %s",
                    "生成段过时 %d,记忆超预算 %d,inbox %d 条,记忆目录 %s"),
    "NONE": ("(none)", "(无)"),
    # review-input
    "RI_LEVEL": ("Review level: %s", "审查档:%s"),
    "RI_CMD_TIMEOUT": ("review failed: review.cmd gave no response within 600 seconds", "审查失败:review.cmd 600 秒内没有响应"),
    "RI_CMD_FAILED": ("review failed (exit code %d): %s", "审查失败(退出码 %d):%s"),
    "RI_EMPTY": ("no differences from the base, nothing to review", "和基准没有差别,没有可审的"),
    "RI_MUST": ("Must review (never skipped)", "必审(任何档都不省)"),
    "RI_ALLOW": ("new allow: %s", "新增 allow:%s"),
    "RI_FROZEN": ("newly frozen rule id: %s", "新冻结的规则号:%s"),
    "RI_LOOSEN": ("loosened %s: %s", "放宽 %s:%s"),
    "RI_UNEXEC": ("not executed, cannot verify (cmd rules are not run here) %s: %s", "未执行,无法核对(这里不跑 cmd 规则) %s:%s"),
    "RI_FINDINGS": ("New findings (frozen ones are not listed; the script already checked them, do not re-check by hand)", "新增红黄项(存量不列;脚本已查,不用人工复查)"),
    "RI_LESSONS": ("Lessons whose paths match the changed files", "路径命中改动文件的教训"),
    "RI_DIFF": ("Diff", "Diff"),
    "RI_FRAGMENT": ("Design fragment", "设计片段"),
    "NOT_GIT": ("%s is not in a git repository (file list and dependencies use git ls-files)",
                "%s 不在 git 仓库里(文件清单和依赖靠 git ls-files)"),
    # git hook / guard
    "DR_GITHOOK_OK": ("git hooks wired (pre-commit, pre-merge-commit; managed by %s, hook dir %s, launcher %s)",
                      "git 钩子已接入(pre-commit、pre-merge-commit;接入方式 %s,钩子目录 %s,启动器 %s)"),
    "DR_GITHOOK_OFF": ("git hooks switched off by nomess hooks uninstall (stub launcher). Fix: nomess hooks install to switch them on again",
                       "git 钩子已被 nomess hooks uninstall 停用(启动器是存根)。恢复:nomess hooks install"),
    "DR_CACHE": (".nomess/cache/: %d files, %s (safe to delete, rebuilt by the next check)", ".nomess/cache/: %d 个文件,%s(可随时删,下次检查重建)"),
    "DR_GITHOOK_BAD": ("git hooks not wired (%s) in %s (managed by %s, hook dir %s, launcher %s); only CI checks commits. Fix: run nomess hooks install there (it prints what to add for husky / the pre-commit framework)",
                       "git 钩子未接入(%s),位置 %s(接入方式 %s,钩子目录 %s,启动器 %s),只有 CI 管提交。修法:在那里跑 nomess hooks install(husky、pre-commit 框架会打出要加的配方)"),
    "GH_B2": ("nomess: %s exists in HEAD but this commit deletes it; that turns the gate off (loosening). Restore it, or go through the loosening review",
              "nomess: 这次提交删掉了 HEAD 里有的 %s;删配置等于关掉检查(放宽),先恢复它,确要停用走放宽流程"),
    "GH_RED": ("nomess: %d new red finding(s), first %s:%s %s %s; details: nomess check --red", "nomess: %d 条新红项,首条 %s:%s %s %s;详情跑 nomess check --red"),
    "GH_SKIPPED": ("nomess: generated file %s not refreshed (%s); run nomess refresh and add it yourself",
                   "nomess: 生成物 %s 没有刷新(%s);手动 nomess refresh 后自己暂存"),
    "GH_SKIP_NOTREG": ("not a regular file", "不是普通文件"),
    "GH_SKIP_ATTR": ("working-tree-encoding or filter is set", "设了 working-tree-encoding 或 filter"),
    "GH_SKIP_DIRTY": ("it has unstaged changes", "有未暂存改动"),
    "GH_ADD_FAIL": ("nomess: writing the refreshed files into the index failed, commit aborted; nothing was changed: %s",
                    "nomess: 刷新结果写进索引失败,提交中止;索引和工作区都没动:%s"),
    "GH_WT_FAIL": ("nomess: the refreshed files are in the commit, but writing them to the working tree failed (run nomess refresh): %s",
                   "nomess: 刷新结果已进提交,但写回工作区失败(跑 nomess refresh 补上):%s"),
    "GH_RED_NOTE": ("nomess wrote none of its generated files before reporting; cmd rules must only check and never modify files",
                    "报红前 nomess 没写任何生成物;cmd 规则必须只检查、不改文件"),
    "GH_RED_MERGE": ("the merge is still in progress: fix it and git commit, or undo it with git merge --abort",
                     "合并还停在半路:修好后 git commit,或 git merge --abort 撤销"),
    "GH_MERGE_ORDER": ("pre-merge-commit: nomess must run before any step that changes the index; if that order cannot be guaranteed, merge with git merge --no-commit and finish with git commit",
                       "pre-merge-commit:nomess 必须在任何会改索引的步骤之前运行;保证不了顺序就用 git merge --no-commit 再 git commit 收尾"),
    "GH_INST_INSTALLED": ("%s: installed", "%s: 已安装"),
    "GH_INST_KEPT": ("%s: already wired", "%s: 已接入"),
    "GH_INST_OTHER": ("%s: there is already a hook that is not nomess's; not overwritten. Add this to it (the exit code must pass through, no `|| true`):",
                      "%s: 已有别人的钩子,没有覆盖。把下面这段加进去(退出码要原样传出,不要加 `|| true`):"),
    "GH_UNINSTALLED": ("nomess git hooks removed", "nomess 的 git 钩子已移除"),
    "GH_STATUS": ("launcher %s (present: %s); managed by: %s; hook dir %s; hooks: %s",
                  "启动器 %s(存在: %s);接入方式: %s;钩子目录 %s;钩子: %s"),
    "GH_STUB": ("switched off (stub)", "已停用(存根)"),
    "GH_RECIPE_HUSKY": ("husky owns the hooks: add this to the user script .husky/%s (create it if missing; never edit .husky/_):",
                        "husky 管着钩子:把下面这段加进用户脚本 .husky/%s(没有就新建;不要改 .husky/_):"),
    "GH_RECIPE_FRAMEWORK": ("the pre-commit framework owns the hooks: add this to .pre-commit-config.yaml, then run the install command:",
                            "pre-commit 框架管着钩子:把下面这段加进 .pre-commit-config.yaml,再跑最后那条安装命令:"),
    "GH_YES": ("yes", "是"),
    "GH_NO": ("no", "否"),
    "GUARD_BYPASS": ("nomess: %s bypasses the commit gate; commit without it (fix the finding instead)",
                     "nomess: %s 会绕过提交检查;去掉它再提交(要修的是红项)"),
    "GUARD_UNWIRED": ("nomess: the %s git hook is not wired (removed, or not executable); run nomess hooks install first",
                      "nomess: git 钩子 %s 没接上(被移除或没有执行权限);先跑 nomess hooks install"),
    "GUARD_NEVER": ("nomess: git hooks are not installed in this clone, so commits are not checked locally; run nomess hooks install",
                    "nomess: 这个克隆没装 git 钩子,本地提交不会被检查;跑 nomess hooks install"),
    "GIT_IN_BLOCK": ("git %s inside a loop or script block", "git %s 在循环或脚本块里"),
    "GIT_VIA": ("git called through %s", "经 %s 转手调用 git"),
    # doctor
    "DR_OK": ("ok", "通过"),
    "DR_WARN": ("warn", "提示"),
    "DR_FAIL": ("FAIL", "失败"),
    "DR_CLAUDE_OK": ("Claude Code %s (need %s or newer)", "Claude Code %s(要求 %s 及以上)"),
    "DR_CLAUDE_OLD": ("Claude Code %s is older than the required %s. Fix: update Claude Code", "Claude Code %s 低于要求的 %s。修法:升级 Claude Code"),
    "DR_CLAUDE_NONE": ("claude command not found on PATH, cannot check the version (need %s or newer)",
                       "PATH 上没有 claude 命令,无法检查版本(要求 %s 及以上)"),
    "DR_PY_OK": ("Python %s (running doctor)", "Python %s(运行 doctor 的这个)"),
    "DR_PY_OLD": ("Python %s is older than 3.9. Fix: install Python 3.9+ and pick it in /config", "Python %s 低于 3.9。修法:装 Python 3.9+,并在 /config 里选它"),
    "DR_HOOKPY_OK": ("hook interpreter '%s' works (Python %s)", "钩子用的解释器 '%s' 可用(Python %s)"),
    "DR_HOOKPY_MISSING": ("hook interpreter '%s' not found or not runnable, hooks cannot start. Fix: on macOS / Linux pick python3, on Windows python (or py) in /config; the interpreter must be on PATH",
                          "钩子用的解释器 '%s' 找不到或跑不起来,钩子起不来。修法:在 /config 里改,macOS / Linux 选 python3,Windows 选 python(或 py),且要在 PATH 上"),
    "DR_HOOKPY_UNSET": ("hook interpreter not found in ~/.claude/settings.json pluginConfigs (checked with --python to override). Fix: run /config and set the nomess python option",
                        "在 ~/.claude/settings.json 的 pluginConfigs 里没找到钩子解释器(可用 --python 指定)。修法:/config 里设置 nomess 的 python 选项"),
    "DR_GIT_OK": ("git %s", "git %s"),
    "DR_GIT_NONE": ("git not found on PATH. Fix: install git", "PATH 上没有 git。修法:装 git"),
    "DR_CFG_OK": ("nomess.json readable: %s", "nomess.json 可读:%s"),
    "DR_CFG_NONE": ("no nomess.json found at or above %s. Fix: run /nomess:init", "从 %s 往上没找到 nomess.json。修法:跑 /nomess:init"),
    "DR_CFG_BAD": ("nomess.json is not valid: %s. Fix: correct the file", "nomess.json 不合法:%s。修法:改正这个文件"),
    "DR_HOOK_OK": ("pre-commit hook runs (silent on a non-git command)", "提交前钩子能跑(非 git 命令零输出)"),
    "DR_HOOK_BAD": ("pre-commit hook failed to run with '%s': %s. Fix: check the interpreter and the plugin install",
                    "提交前钩子用 '%s' 跑不起来:%s。修法:检查解释器和插件安装"),
    "DR_IMPORT_OK": ("CLAUDE.md imports AGENTS.md", "CLAUDE.md 已导入 AGENTS.md"),
    "DR_IMPORT_NA": ("no AGENTS.md, nothing to import", "没有 AGENTS.md,无需导入"),
    "DR_IMPORT_ALONE": ("AGENTS.md without CLAUDE.md (Claude Code reads AGENTS.md directly)", "有 AGENTS.md、没有 CLAUDE.md(Claude Code 直接读 AGENTS.md)"),
    "DR_IMPORT_BAD": ("CLAUDE.md does not import AGENTS.md, Claude Code will not read it. Fix: add a line `@AGENTS.md` to CLAUDE.md",
                      "CLAUDE.md 没有导入 AGENTS.md,Claude Code 不会读它。修法:在 CLAUDE.md 里加一行 `@AGENTS.md`"),
    "DR_SUMMARY": ("nomess doctor: %d problems", "nomess doctor: %d 个问题"),
}
