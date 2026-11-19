# nomess 脚本

日常只用 `nomess refresh`(生成段、系统图、路径规则一次写完);`docgen`、`map`、`rules` 用来单独刷新某一项,各自带 `--check` 只比对不写(`refresh` 没有 `--check`)。

`nomess <check|refresh|docgen|map|rules|lessons|status|doctor|init|off|dream> [参数]`(`bin/nomess`、`bin/nomess.cmd`,或 `python scripts/nomess.py`)。只用标准库;过了不出声;从当前目录往上找 `nomess.json`,路径都相对它。退出码:0 通过,1 有新红项或过时,2 运行故障(配置不对、超时、生成器失败)。`map` 的文件清单和依赖靠 `git ls-files`,项目要在 git 仓库里。

## nomess.json

```json
{"format": "nomess/1",
 "main_branch": "main",
 "lang": "en",
 "systems": {"core": ["src/core/*"], "net": ["src/net/*"]},
 "docgen": {"events": {"file": "docs/design.md", "map": "events"},
            "entry": {"file": "AGENTS.md", "builtin": "agents-entry"}},
 "map": {"events": {"title": "事件", "columns": ["事件"], "glob": "src/**/*.py",
                    "regex": "EMIT\\(\"(\\w+)\"\\)", "file_col": true, "misses": "动态事件名",
                    "hotspot": {"by": "事件", "max": 1, "label": "同一事件多处发"}},
         "index_tokens": 1500},
 "check": {"baseline": ".nomess-baseline.json",
  "rules": [
   {"id": "R1", "level": "red", "what": "查什么", "why": "防什么", "glob": "src/**/*.py", "forbid": "\\bprint\\("},
   {"id": "R2", "level": "yellow", "what": "...", "why": "...", "glob": "src/*.py", "require": "^# Copyright"},
   {"id": "R3", "level": "red", "what": "...", "why": "...", "cmd": ["python", "tools/x.py"]}]},
 "allow": [{"rule": "R1", "file": "src/cli.py", "reason": "必填"}],
 "memory": {"index_tokens": 2000, "page_tokens": 1500, "title_ratio": 0.8},
 "rules": {"file_tokens": 400},
 "review": {"level": "standard", "cmd": ["python", "tools/review.py"]},
 "lessons_dir": "docs/lessons"}
```

| 键 | 内容 | 谁用 |
|---|---|---|
| `main_branch` | 主分支名;**必填,缺了报错**(退出 2) | P3 hook、`/nomess:review` |
| `lang` | `en`(缺省)或 `zh-CN`:脚本提示语的语言、`lessons add` 写出的字段名和状态词、生成文件里的固定文字。别的值报错(退出 2) | 全部子命令 |
| `size` | `small`(缺省)/ `medium` / `large`:决定 `check.builtin`、`review.level` 的缺省值 | `nomess check`、init |
| `check.rules` / `check.baseline` / `check.builtin` | 检查规则;基线文件(`nomess-baseline/2`);要开的内置检测号(缺省跟 `size`) | `nomess check` |
| `smells` / `scopes` / `allow` / `arch` | 阈值;按目录覆盖;唯一的例外家;子系统间约束。全部键和缺省值见 `nm_config.DEFAULTS` 和下面"检测器和模块" | `nomess check` 等 |
| `docgen` | 生成段名 → `{file, map / cmd / builtin 三选一}` | `nomess docgen` |
| `map` | 抽取表:title、columns、glob、regex、file_col、misses、可选 `hotspot: {by, max, label}`;另有 `index_tokens`(整数,系统图首页预算,缺省 1500)、`page_tokens`(整数,`files.md`/`deps.md` 单页预算,缺省 8000),都不是表 | `nomess map` |
| `systems` | 子系统名 → 非空的路径 glob 列表(glob 语义同规则文件,见 rules);没填就按源文件所在的顶层目录划(隐藏目录、只有文档的目录不算) | `nomess map`、`nomess rules`、说明页检查 |
| `memory` | 预算覆盖(见下) | `nomess check --memory` |
| `rules.file_tokens` | 每份规则文件的预算(估算 token),缺省 400 | `nomess rules`、check |
| `review.level` | `off` / `light` / `standard` / `strict`(`off` 完全不审),缺省跟 `size`,别的值报错 | workflow、`/nomess:review` |
| `review.cmd` | 外部审查命令(列表) | `nomess review-input --cmd` |
| `docs_root` | 项目文档根,缺省 `docs`;7 类文档、`system-map/`、教训库缺省目录都在它下面。`init --auto` 认出 `docs/` 是文档网站源时设成 `project-docs` | 文档检查、map、init |
| `lessons_dir` | 缺省 `<docs_root>/lessons` | `nomess lessons` |
| `dev_docs` / `public_docs` | 开发者文档 / 对外文档的 glob,追加在内置的之上(内置:dev = 根目录 `CONTRIBUTING*` `HACKING*` `DEVELOPMENT*`;public = 根目录 `README*` `CHANGELOG*` `LICENSE*` `SECURITY*` `CODE_OF_CONDUCT*`);两档都中算对外。两档都只查断链(黄);dev 整理时只许就地修改,public 整理绝不改。去掉条目算放宽;`docs_root` 或 `lessons_dir` 落进对外文档是配置错误 | 文档检查、dream |
| `doc_types` | 额外文档类型 `[{"name", "what", "dir" 或 "file", "role"}]`:`dir` 是 `docs_root` 下一层目录、`file` 是 `docs_root` 下一层的 `.md`,二选一,不和内置类型和彼此重叠(`file` 也不许占内置的单文件位置);`name`、`what` 必填,写错退出 2;登记后该位置的 `.md` 合法、进目录段。`role`(`overview` / `systems` / `schedule` / `plans` / `ownership`,每个最多一条)只在 `builtin_doc_types: false` 时许写,表示这一类沿用内置的那项功能:`overview` 挂目录段(必须有、必须是 `file`、不许落进对外文档;重跑 `init --auto` 会把 docs-index 登记改到它)、`systems` 给代码地图链说明页和 DOC3 / DOC7 / 系统页"坑"段用(`dir`)、`schedule` 给 C4 对账(`file`)、`plans` 给方案检查和 PL-STALE(`dir`,`<dir>/archive` 是归档)、`ownership` 只登记位置(`file`);某个 role 没有条目,那项功能静默不跑。教训库和系统图永远在、不进表。删条目、改位置或挪 role 算放宽;新增一条进 review-input 必审 | 文档检查、guard |
| `builtin_doc_types` | 缺省 `true`:内置 7 类 + `doc_types` 追加。`false`:只认 `doc_types` 表(`init --auto --docs custom` 会把 5 个可编辑内置类型展开写进去),`doc_budget` 只认条目名(带 role 的缺省预算按 role 取)。true 改 false 算放宽 | 文档检查、guard、dream |
| `doc_places` | 缺省 `"strict"`。`"free"`:DOC4 不报、guard 不挡、整理不挪散放的页,入口段改说"优先放进";目录段照旧按类型分组,不在类型位置的列进"未归类"(不算孤儿);DOC5/6/7 照旧。strict 改 free 算放宽 | 文档检查、guard、dream |
| `doc_budget` | 类型代号(`overview` `systems` `lessons` `schedule` `plans`)或登记类型名 → DOC6 的 token 预算,缺省值在 `doctypes.BUDGETS`(3000 / 3000 / 3000 / 4000 / 6000);调大算放宽 | DOC6 |
| `lessons_remind` | 自动整理的 inbox 线,缺省 10 | dream |
| `dream` | `auto`(没写按 false;`init` 新建的配置写 true,老配置要自己开;关着时会话钩子不触发整理)、`stale_days`(inbox 最老条目到线天数,缺省 30)、`max_items`(工作清单上限,缺省 20) | dream、会话钩子 |

- **docgen**:文档里放 `<!-- GEN:名字 BEGIN -->` / `<!-- GEN:名字 END -->` 各占一行;标记之外的字节不动(CRLF 文件保持 CRLF)。生成器:`map`(抽取表名)、`cmd`(列表;标准输出即正文,**须输出 UTF-8**,Python 子进程自动设好;缺省超时 60 秒,可写 `timeout`)、`builtin`:`lessons-index`(教训库每个主题页一行,每个主题页的条数)、`memory-index`(另写 `"dir"`:记忆目录,每个主题页一行)、`docs-index`(`<docs_root>/overview.md` 末尾的全部文档目录:按类型分组,每页一行标题和开头第一句,方案带状态、被取代的写取代者,再列未归类、开发者文档、对外文档;超 1,500 token 时归档方案收成"N 份 + 最新 5 份";init 模板已登记)、`agents-entry`(`AGENTS.md` 的 nomess 段,固定 5 行:设计总览和系统图首页在哪、提交前自动检查、教训怎么查、文档只放哪些位置(按类型表生成,含登记类型)、文档只写现在的样子;有 `<docs_root>/schedule.md` 的大项目多 1 行会话协议;上限 12 行)。`nomess docgen [--check] [名字]`,内容没变不写文件。
- **map**:`nomess map [--check]` 写 `<docs_root>/system-map/`:`index.md`(分页链接、重叠热点清单加末行“屎山存量 N”(已冻结的检查发现数)、子系统一行一条、子系统依赖 Mermaid 图)、`files.md`(`git ls-files` 加头注释第一句)、`deps.md`(仓库内文件依赖,按扩展名认 Python / JS·TS / C·C++ / Go / Rust / C#)、每张抽取表一页;`size` 为 `small` 时只出首页(不带分页链接);`files.md`、`deps.md` 超 `map.page_tokens` 时,`files.md` 收成每个目录一行(文件数),`deps.md` 只列跨子系统的边。全部生成、不手改;`--check` 只比对。**首页有 token 预算**(`map.index_tokens`,缺省 1500):超了按固定顺序裁,先把子系统依赖图收成只留参与跨子系统依赖的节点(图本来就只画跨子系统的边),再把热点清单只留最重的 10 条(按涉及文件数,同数按文字)并写“其余 N 条见分页”;同样输入输出一字不差。裁完仍超预算,check 报黄 MAP1。没填 `systems` 时按源文件所在的顶层目录划子系统。抽取表每个正则捕获组一列(没匹配到的可选组为空)、每处匹配一行;`hotspot` 按 `by` 列分组,不同文件数超过 `max` 进热点清单(需 `file_col`);依赖里被超过 `smells.fan_in` 个文件依赖的文件也进热点。表名不能叫 index / files / deps。
- **check**:`forbid` 匹配的行报,`require` 匹配不到的文件报,`cmd` 非零退出报;例外只写顶层 `allow`(见下节);`glob` 和 `allow.file` 的语义同 rules(pathglob.py,支持 `{a,b}`;`*.py` 不带 `/` 匹配任意层),只在 git 管着的文件(`git ls-files -co --exclude-standard`)里匹配,`map` 抽取表的 `glob` 也一样;红退出码 1,黄只显示。基线、`--freeze` / `--tighten` / `--ci` 见下节"检测器和模块";`--red` 是钩子跑的那一套、只列红项;`--rules` 列规则;`--all` 不截断(缺省最多 5 行,存量只计数)并逐条列存量;`--json` 输出数组,每项 `level`(red / yellow)、`rule`、`file`、`line`、`msg`、`state`、`frozen`;`--no-exec` 不运行项目里的任何代码(跳过 `cmd` 规则和 cmd 生成器,做梦出提案用)。`--red` 也查红 L5。内置检查不用登记:生成段和系统图过时(黄 GEN)、docs 断链(红 DOC1)、系统说明页缺 `这是什么：` / `为什么要有：` / `和谁配合：` 三行头(黄 DOC3)、新文件缺头注释(黄 HDR,缺省关,`check.builtin` 写了才开)、未核实教训条数(黄 L1)、文档根下不在任何类型位置的 `.md`(DOC4:本次新增红、存量黄,提示带最像的位置)、从总览走不到的孤儿页(黄 DOC5)、超 `doc_budget`(黄 DOC6)、改了子系统源文件而它的说明页没改(黄 DOC7,只按真实改动判)、inbox 结构坏了(红 L5)、标题几乎相同(黄 L4)、规则文件(见 rules)、方案头、`AGENTS.md`、系统图首页预算。
  - **方案头**(`<docs_root>/plans/**/*.md` 开头 12 个非空行里的 `状态:` / `取代:` / `被取代:`):`取代` / `被取代` 指向不存在的文件(相对方案文件所在目录)红 PLN1;`docs/plans/archive/` 下的方案缺 `状态:`、或写了 `被取代:` 而状态不是 `已被取代` 黄 PLN2。
  - **AGENTS.md**:整个文件约超 1,500 token 黄 AGENTS1;有 `AGENTS.md` 和 `CLAUDE.md` 但 `CLAUDE.md` 里没有单独一行 `@AGENTS.md` 黄 AGENTS2(Claude Code 有 `CLAUDE.md` 就不读 `AGENTS.md`)。
  - **系统图首页**超 `map.index_tokens` 黄 MAP1。
- **check --memory 目录**:预算按估算 token(中文按字数,其余字符数/4)。索引超预算(M2)、主题页超预算(M3)只报黄;未核实条目数报黄(M6);标题几乎相同报黄(M7:标题取索引里 `[标题](文件)` 的链接文字,没列进索引的页用文件名;去大小写、空白、标点后 difflib 相似度 ≥ `title_ratio`,缺省 0.8,教训库体检 L4 共用);断链(`[[页名]]` 和相对链接,M5)、子目录超过两级(M4,`archive/`、`.trash/`、`.git/` 除外)、没有 `MEMORY.md` / `INDEX.md`(M1)报红。阈值取 `expanded(cfg)["memory"]`,`memory` 段可覆盖 `index_tokens`、`page_tokens`、`title_ratio`。
- **lessons**:`<lessons_dir>/*.md`,每条 `## 标题` 加 `键: 值` 行,写出顺序:`概述`(何时适用,含路径和关键词)、`状态: 已核实|未核实`、`更新: YYYY-MM-DD`(add 自动写)、`路径: glob, glob`(可选,升成规则时写)、`规则: 一句话`(可选)、`内容: ...`(最后一栏,可跨多行)。代码围栏(``` / ~~~)里的行不当标题和键。旧版写的 `日期:` 读作 `更新:`。`find 关键词...`(最多 3 条,未核实的标“(未核实)”;路径分隔符 `\` 与 `/` 等价;别名命中和标题同权重;参数是仓库里的文件时另加分:条目 `路径:` 匹配 +10、同子系统 +4 标 `[同模块]`、它直接依赖的子系统 +2 标 `[依赖 <名>]`,只取一层、不取反向)、`add 标题 -s 概述 -b 内容 [-k 别名] [--external 出处] [--unverified]`(`-k` 写 `别名:` 行,逗号分隔;`--external` 写 `来源: 外部 <出处>` 并强制未核实;缺省写已核实;**库里已有同标题条目(忽略大小写和空白)时原地覆盖它**并更新 `更新`、输出“已覆盖”,保留它的路径 / 规则,旧说法靠 git 历史留着,否则追加进 `inbox.md`)、`status`(inbox 条数、最早一条距今天数、未核实条数)。`inbox.md` 结构坏了报红 L5(钩子里也查):同一条里同一个键出现两次(`merge=union` 合并拼出的交错字段),或标题忽略大小写和空白后重复,由合并的人解决。找不到 `nomess.json` 报错,不建库。
- **rules** [`--check`]:从教训条目(`inbox.md` 除外)和 `<docs_root>/systems/*.md` 里 `## 坑`(或 `## Pitfalls`)段下的 `### 标题` 条目,凡带 `路径:` 和 `规则:`、且 `状态:` 明确是已核实的,生成 `.claude/rules/nomess/<8 位哈希>.md`。没写状态或未核实的不生成。**路径集合相同的条目进同一个文件,文件的 `paths` 就是条目自己写的 glob**(不按子系统放大范围);文件名是这组 glob 的 sha1 前 8 位。glob 语义对齐 Claude Code(https://code.claude.com/docs/en/memory#path-specific-rules):不带 `/` 的(如 `*.py`)匹配任意层,`/` 开头的只在项目根,带 `/` 的从项目根算、`*` 不跨 `/`,`**` 任意层目录,`{a,b}` 展开(最多 1000 个),`[abc]` 字符组,`\[` 转义;`!` 取反、`/` 结尾、`[` 不配对不支持(RUL5)。文件格式固定:frontmatter 只有非空的 `paths`(YAML 列表,双引号),一行生成提示,之后每条一行 `- <规则> → <文件>#<标题>`。内容没变不写;没有条目时清掉旧文件和空目录;只动 `.claude/rules/nomess/`,写和删之前确认这个目录和目标文件都不经过符号链接 / junction,经过就报错不写。`--check` 只比对,过时退出码 1。check 报:红 RUL1(frontmatter 不是生成的格式,会变成常驻加载)、黄 RUL2(过时)、RUL3(超 `rules.file_tokens`)、RUL4(glob 在 `git ls-files` 里匹不到任何文件)、RUL5(只写了路径或规则之一 / 状态不是已核实 / glob 不支持 / 规则超 40 字或 25 词)。主分支提交后的 hook 也会跑它。
- **init --auto** [`--lang en|zh-CN`] [`--size small|medium|large`] [`--docs standard|free|custom`]:零 token 启用,什么都不问:建 `nomess.json`(主分支取 `origin/HEAD` → 本地 `main` / `master` → 当前分支,分离头指针退出 2)、`AGENTS.md` 的 nomess 段和"环境和运行"标题、`CLAUDE.md` 导入、`.gitignore` / `.gitattributes` 几行、`<docs_root>/overview.md`(带 `docs-index` 目录段),再 refresh、`check --freeze`、`hooks install`。认出文档网站源(mkdocs、docusaurus、Sphinx、vitepress、mdBook、Jekyll)时把它整体登记进 `public_docs`,源目录就是 `docs/` 时 `docs_root` 设成 `project-docs`。`--docs`(只在新建 `nomess.json` 时用,缺省 standard):standard 不写新键;free 写 `"doc_places": "free"`;custom 写 `"builtin_doc_types": false` 并把 5 个可编辑内置类型展开成带 role 的 `doc_types` 条目(名字按 lang),人在 `nomess.json` 里删、改名、改位置、加新类。已有文件只补缺的,重跑无害;`--size` 只许调大;不提交;最后打一行给 AI 转述。**off**:`hooks uninstall` + `git config --local nomess.auto false`(会话钩子从此不出声),列出 init 建过的文件供手删;`init --auto` 会清掉这个标记。
- **dream** `begin | land | abort | git-log <词>`:自动整理的脚本部分(`dream.py`)。`begin` 抢锁(`<git 公共目录>/nomess-dream.lock`,2 小时算死锁)、在 `.nomess/dream` 建基于 HEAD 的临时 worktree、记忆目录先提交一次存底、打印工作清单(inbox、标题近似、未核实、记忆超预算、DOC4–6、方案类、排期已合行、文档根外散落 `.md`、过时引用、文档缺口;最多 `dream.max_items` 条,末尾"还有 N 条下次");锁被占退出 3。`land`:worktree 里 `nomess.json` 被改过就丢弃;refresh;护栏(只许碰文档根和教训目录的 `.md`、已有开发者文档的修改、`AGENTS.md` 生成段、`.claude/rules/nomess/`、`.nomess/dream-notes.md`;外部来源条目不许转正或去掉来源行;`check` 不许有红)不过整次丢弃;在 worktree 提交(走 pre-commit)后 cherry-pick 回当前分支,主检出有暂存内容、碰到的文件有未提交改动或冲突就放弃,不重试;最后打印一句带撤回命令的总结并存进状态(`<git 公共目录>/nomess-dream.json`),会话钩子下次补说。`git-log <词>` = `git log -S<词> --oneline -n 20`,给整理的 AI 核实用。`due()`(会话钩子调):`dream.auto` 开、HEAD 里有 `nomess.json`、不在分离头指针、今天没试过、内容指纹变过、任一信号到线(inbox ≥ `lessons_remind` 或最老 ≥ `stale_days` 天、标题近似 ≥ 3 对、未核实 ≥ 10、记忆超预算、DOC4 存量 ≥ 5、有 DOC6、有已合排期行、有散落 `.md`、有文档缺口条目、上次没清完)。
- **status** [`--json`] [`--no-exec`] :一行概览——生成段过时数、记忆超预算数、inbox 条数、项目记忆目录路径。记忆目录按 Claude Code 的规则定位:settings 的 `autoMemoryDirectory` > `CLAUDE_CODE_PROJECT_DIR_NAME`(配合 `CLAUDE_CONFIG_DIR`)> `<配置目录>/projects/<git 主仓库路径,非字母数字换成 ->/memory`;定不下来(不存在、大小写不同的同名目录不止一个)为空,不往上级猜。`--no-exec` 时过时数不跑 cmd 生成器。JSON 键:`stale`、`memory_over`、`inbox`、`memory_dir`、`memory_source`(怎么定的)、`memory_problem`(定不下来的原因)、`lessons_dir`。

## 跨平台和双语(P9)

- **Python 3.9+**:`nomess.py` 入口先查版本,低于 3.9 打一行 `nomess: Python 3.9+ required` 退出 1。不用 3.10 才有的接口(如 `glob(root_dir=)`)。
- **字节级一致**:脚本读写文件一律显式 UTF-8、写出一律 `\n` 换行,标准输出重设成 UTF-8 + `\n`,输出里的路径一律 `/`。`tests/golden.json` 存一个假仓库(英文、中文各一份)生成物的 sha256;`python tests/run.py` 每次重新生成并比对,所以 Windows / macOS / Linux 各跑一遍等于比对过逐字节相同。有意改了生成格式就跑 `python tests/run.py --write-golden` 重写。
- **提示语**:全部在 `scripts/messages.py` 一张表(键 → 英文、中文),按 `lang` 输出;规则号(R1、GEN、DOC1 ...)不随语言变;`--json` 的 `rule` / `file` / `line` 不变,`msg` 随语言。check 的级别词:`red` / `yellow`(中文 红 / 黄)。命令行 `-h` 的说明一律英文。
- **固定字段名中英都认**(精确大小写),写出按 `lang`:

| 用在 | 英文 | 中文 |
|---|---|---|
| 教训条目 | `When:` `What:` `Status:` `Updated:` `Paths:` `Rule:` `Aliases:` `Source:`(外部来源的值以 `external` 开头);状态值 `verified` / `unverified` | `概述:` `内容:` `状态:` `更新:` `路径:` `规则:` `别名:` `来源:`(`外部`);`已核实` / `未核实` |
| 系统说明页三行头 | `What:` `Why:` `Works with:` | `这是什么：` `为什么要有：` `和谁配合：` |
| 方案头 | `Status:` `Supersedes:` `Superseded-by:`;状态值 `proposed` `accepted` `rejected` `superseded` | `状态:` `取代:` `被取代:`;`提案` `已采纳` `已否决` `已被取代` |
| 总排期表 | 列 `Package` `Depends` `Status`;状态 `Todo` `Doing` `Review` `Merged` | 列 `包` `依赖` `状态`;状态 `待派` `在做` `待审` `已合` |

  中英混用的库也能读:两种写法解析出同一个结果(状态在内部归成 `verified` / `unverified`)。
- **nomess doctor** [`--python 名字`]:零 token 自检,每项一行 `ok|warn|FAIL  说明`,FAIL 带一句 `Fix:` 修法;有 FAIL 退出码 1。查 Claude Code 版本(要求 2.1.277 及以上:取直接执行的 hook、`userConfig` 的 `options`〔2.1.271〕、直接读 `AGENTS.md`〔2.1.277〕里最高的;`claude` 不在 PATH 上只提示)、运行脚本的 Python、钩子用的解释器(读 `~/.claude/settings.json` 的 `pluginConfigs`,或 `--python` 指定;选错或没装报 FAIL)、git、`nomess.json` 能不能读、提交前钩子能不能跑、`CLAUDE.md` 有没有导入 `AGENTS.md`。
- **Claude Code 钩子**(`hooks/`):`session.py`(SessionStart,零 token;没事不输出,有事打一行英文:没启用时让 AI 第一次改文件前先用一句话问用户文档怎么管(标准 / 不管位置 / 自己列类型),再带 `--docs` 跑 `init --auto`;上次整理的总结没告诉用户时让 AI 转告;`dream.due()` 为真时让 AI 后台调 `nomess:dream`;不在 git 仓库、设了 `CI`、`nomess.auto=false`、`userConfig.auto_init` 关时都不出声)。`guard.py`(PreToolUse):挡绕过提交闸门、挡 Write 新建不在类型位置的文档;另对三类调用回 allow 免弹窗:本插件 `nomess.py` 的白名单子命令(`dream`、`init --auto`、`lessons find|add|status`、`status`、`check`(不带 `--freeze`)、`doctor`)、整理 worktree 里 `dream.writable` 认可的文件、子代理写项目记忆目录里的 `.md`。
- **CI**:仓库根 `.github/workflows/test.yml`,Windows / macOS / Ubuntu × Python 3.9 和最新版,跑 `tests/run.py` 和 `tests/test_hooks.py`。

## 检测器和模块(P21 定的接口;后四包只往里加,不改含义)

### 检测器登记(`check.py`)

- `DETECTORS` 一行一个模块名字符串(带结尾逗号),只在自己的区块里加;`check.detectors()` 每次按当前表 `importlib` 导入。
- 模块提供:
  - `RULES = [{"id", "level", "what", "why"[, "needs", "select", "freeze"]}]`:`what` / `why` 是 messages 键(`--rules` 经 `t()` 列出);`level` 是缺省颜色,每条发现的颜色看发现自己;`needs(eff_cfg) -> bool` 给"登记了才开"的号(A2–A5),不在 `nm_config.BUILTIN`、又没写 `needs` 的号有配置就算启用;`select` = `file`(缺省)或 `edge`,顶层 allow 用 `file` 还是 `from`/`to` 匹配;`freeze: False` 的号不进基线、不能写 allow(结构性诊断如 `REL_EMPTY`)。
  - `run(snap, changes, eff) -> [Finding]`:`changes` 是 `{路径: "A"|"M"|"D"}`(`cand.diff(base)`;全量时全部 A);按文件的检测只查非 D 的,按图的检测用整棵树。`eff(path)` 取单个文件的有效配置,`eff.cfg` 是展开后的整份配置。
  - 产出 `arch.relations` 号(号就是 relation 的 id)的模块另写 `RELATIONS = True`(`--tighten` 据此知道这些号执行过)。
- 分工:检测器管输入资格和计算(scope 阈值、语言、登记了哪些约束,可以跳过 `eff(p)["checks"]` 里没有本号的文件);`check.py` 管开关(以它为准)、颜色、allow、基线、B1、B2、去重。检测器遇到配置错误抛 `ValueError`(退出 2),不吞异常。
- **Finding** 一律 `nm_config.F(level, rule, file, line, text, msg, *, k=None, also=(), metric=None, edge=None, under=None)`:`level` 原始颜色(确定红、启发式黄);`file` 仓库相对路径或 `"-"`;`line` 只显示;`k` 基线键里路径以外的部分(字符串列表,缺省 `[text]`;forbid / require / S1 / P1 / P2 写 `[]`,cmd 规则写失败输出的最后一行,S2 `["Cls.meth"]`,D1 `[指纹]`,A1 排好序的成员,A2–A4 `[from, to]`,关系 `[表.列, 值]`,C4 `[包A, 包B, 路径]`),**路径只放 `file` / `also`**(改名映射只改这两处);`also` 和 `file` 对称的另一边(D1);`metric` 有值是指标类(同一身份只能一条);`edge` `(from, to)`,`select: edge` 的号必填;`under` `(规则号, k)`:那条最终会挡提交时本条不报(A2/A3 落在环上填 `("A1", 环的 k)`)。
- **基线身份** = (原始颜色, `file`+`also` 排好序, `k`):颜色在身份里,黄的额度抵不了红。

### 统一入口 `check.evaluate(cand, base, *, exec_cmd, gate=False, full=False, allow_loosen=False)`

| 入口 | cand | base | exec_cmd | gate | full |
|---|---|---|---|---|---|
| 钩子 | 索引(刷新时是候选 overlay) | HEAD 的树 | 是 | 是 | 否 |
| `nomess check` | 工作区 | HEAD 的树(没有提交为 None) | 不带 `--no-exec` 就是 | `--red` 时 | 是 |
| `nomess check --ci --base X` | HEAD 的树 | X 的树 | 是 | 否 | 否 |
| `review-input` | HEAD 的树 | 基准的树 | **否** | 否 | 否 |

顺序写死:读配置(两边都没有 → `skipped`;基准有、这里没有 → B2)→ 规则号唯一和 allow 合法(否则退出 2)→ 配置和基准不同、有首次冻结的号或 `full` 时全量(对每个文件调一次 `eff`,scope 冲突在这里暴露),否则只查 `cand.diff(base)` → 跑检测 → 开关和颜色(按文件的号:`file` 和 `also` 各看自己的 `eff(x)["checks"]`,任一边开就留,颜色取开着的几边里最严的;tree 类的号只认 `eff.cfg["check"]["builtin"]`)→ allow(`file` glob 匹配 `file` 或任一 `also`;`edge` 匹配 `from`/`to`)→ 基线和状态 → B1 → B2 → 去重 → 改名写回。

返回(形状固定):`{"skipped", "findings"(每条带 state: new | worse | grew | frozen | loosen,以及 frozen), "new_allow", "new_frozen", "review": {"level", "file"} | None, "writes": {路径: bytes}}`。`check.blocking(res)` = 有没有红(只有 new、worse、loosen 可能红)。退出码:配置错误 2,`blocking` 1,否则 0。对外还有 `check.load_baseline(snap, cfg)`(系统图首页的存量 N 用)。

- **状态**:次数类按行序,前面基线那么多条 `frozen`、多出的 `new`;指标类基线里没有 `new`,超过 基线 × (1 + `grow_slack`)(取 `file` 那一边的 `eff`)`worse`,涨了没超 `grew`,其余 `frozen`。`frozen`、`grew` 一律黄。基线里没有的号按空基线判。
- **B1**:已有的号多出身份或数变大;首次冻结(基线里新出现的号)只给基准里没启用、待检里已登记、已启用、允许冻结、本轮实际检查过的号,而且条目必须是本次全量观测的子集(身份在、次数 / 指标不超);基线里不认识的号(两边都算)保留、报 BL1,但不算额度;基准已启用的号按空基线比。
- **B2**:`nm_config.loosened(expanded(基准), expanded(待检))`,判法查 `nm_config.LOOSEN` 表(见下)。B1 / B2 缺省红,`--ci --allow-loosen`(人批准过)降黄,并以待检的基线为准。
- **改名**:`cand.renames(base)` 把基准基线里的旧路径换成新路径再比;待检基线里还写着旧路径时,规范化后的基线放进 `writes`,钩子经 `outwrite.apply` 写回这次提交。
- **保留号**(`check.RESERVED`):`nm_config.BUILTIN` 全部、旧检查号(DOC1、DOC3、HDR、L1、L4、L5、RUL1–5、PLN1–2、AGENTS1–2、MAP1、GEN、M1–7)、诊断号 CFG1、BL1、B1、B2、CMD1,加各检测器 `RULES` 的号;`check.rules` / `arch.relations` 用了就退出 2。诊断号不进基线、不能写 allow;`cmd` 规则不能写 allow。
- **钩子里跑哪些旧检查**(`gate`,和 P20 一致):可能变红的(顶层红,或某条 scope 把它升红)forbid / require / cmd 规则和 HDR,加 RUL1、L5、DOC1、PLN1;cmd 规则读工作区,所以已跟踪文件有未暂存改动时不跑、报黄 CMD1(交给 CI);其余旧黄项、GEN、CFG1 只在非钩子入口跑。登记的检测器和 B1 / B2 各入口都跑。
- **`--ci`**:直接从 git 顶层读两棵树的配置(不靠工作区里的 `nomess.json`),两棵都没有就跳过;和 `--freeze`、`--tighten`、`--rules`、`--no-exec`、`--memory` 互斥(退出 2);工作区要和 HEAD 一致(否则退出 2);不读检出目录里的缓存;待检提交的基线没跟着改名规范化(`writes` 非空)报红 B1,要经钩子提交或手动 `--freeze`。

### 基线文件 `nomess-baseline/2`

```json
{"format": "nomess-baseline/2",
 "rules": {
  "D1": [
   {"file": "src/a.py", "also": ["src/b.py"], "k": ["9f3a"], "level": "red", "n": 1}
  ],
  "S1": [
   {"file": "src/big.py", "k": [], "level": "red", "v": 1203}
  ]}}
```

一行一个条目,规则号和条目都排序,两次生成逐字节相同;`file` 是排好序的第一个路径(没有路径写 `"-"`),`also` 其余;次数类 `n`(非负整数)、指标类 `v`(有限数),二选一。严格解析:旧格式报 `BASELINE_OLD`、字段不对、同号下身份重复都退出 2;不认识的规则号保留并报黄 BL1。冻结过、没有命中的号写空列表。`--freeze` 只给还没有、本轮启用并检查过、允许冻结的号写条目(取全量观测,没过 allow);`--tighten` 先按改名映射改写基线,只动本轮检查过的号,删掉观测不到的身份,数只降不升,没执行的(`--no-exec` 跳过的 cmd、没开的号)原样留。

### 有效配置(`nm_config.py`)

- `expanded(cfg)`:深合并 `DEFAULTS`;`check.builtin`、`review.level` 没写时取 `SIZE[size]`。`DEFAULTS` 同时是合法键表(`"*"` = 名字随用户取的那层的条目样子,只用于认键,不往用户条目里补);列表条目的键在 `ITEM_KEYS`。不认识的键报黄 CFG1(带最近的合法键)。
- `Effective(cfg)`:`eff(path) -> {"off", "checks"(开着的按文件号:BUILTIN 里 file 类的 builtin 号 + forbid / require 规则的 id,按 scope 依次 add / remove), "smells"}`。scope 合并:只看命中的条目,具体程度 = 命中这个文件的 glob 里最具体的一个(第一个通配符前的字面前缀长度,相同再比字面字符总数),从不具体到具体逐键覆盖,不看先后;两条一样具体、命中同一文件、写了同一个键(`smells.x` / `checks.x` / `off`)退出 2。内置测试 scope(`TEST_GLOBS`,关 D1 P1 P2 P5 S1 S2)永远排最前。
- `BUILTIN` 是 `check.builtin` 的词表并标出 file / tree 类;`SIZE` 是三档缺省(小 D1 P1 S1 + light;中加 A1 + standard;大再加 C4 PL-DUP PL-STALE)。
- `LOOSEN`(B2 判法表,表里没有的键不比):`check.builtin`、`smells.extra_ext`、`arch.independent`、`arch.forbid` 只许增;`arch.layers` 只许增且已有层的相对顺序不变;`check.rules`、`arch.relations` 按 id 删或改都算(level 黄改红除外);`check.baseline`、`systems` 任何改动都算;`public_docs`、`dev_docs` 只许增;`docs_root` 任何改动都算;`doc_places`、`builtin_doc_types` 离开缺省值(strict → free、true → false)算;`doc_types` 按位置(dir / file 和路径)比,旧位置没了(删条目、改目录 / 文件、dir 和 file 互换)算,旧 role 没了或挪到别的位置也算,给已有位置加 role、只改名字和说明不算;`smells.*` 阈值变大算;`review.level` 变低算;`map.*` 已有表的 glob / regex / columns 改动、`may_be_empty` 改成 true、删表算;`scopes` 按 glob 比:glob 增删(改名 = 一删一增)算,同一 glob 下两边都有的键变松算,只写一边的键除"新加最严的(checks.add、off false)/ 删掉最松的(checks.remove、off true)"外都算。后四包要加键只在自己的区块里加行。

### 提示语和缓存

- `messages.add(table)`:模块顶层 `M = {键: (英文, 中文)}`,下一行 `messages.add(M)`;先整表校验(键重名、值不是两个字符串 → `ValueError`)再合并;`t()` 仍是唯一出口。键前缀:clones `CL_`、smells `SM_`、arch `AR_`、deps `DP_`、map `MP_`、plancheck `PC_`。新字段名:`NAMES["sched_col"]["files"]`(可改文件)、`NAMES["plan_head"]["systems"]`(系统)。
- `cache.facts(snap, path, kind, version, fn)`:返回 `fn(text)`(UTF-8 解码、`\r\n` 换成 `\n`);键 = (内容对象名, kind, version):索引 / 树用条目 oid(命中不读文件),工作区 / 叠加内容读一次字节、用 `snapshot.blob_hash` 算,同一份字节交给 `fn`。读不到返回 None、不调 `fn`。fn 的结果还依赖别的(扩展名、表配置)就写进 kind 或 version。存 `.nomess/cache/<sha1(json [kind, version])>.json`(文件里存 kind、version,读时核对;返回的是副本),进程退出时原子写;不加锁、不回收、不删别的版本,读写出错只当没命中,目录可随时删。只存单个文件就能得到的原始事实(设计稿 ⑥ 第 4 小节)。
- 快照新读取方法:`snap.oid(path)`、`snap.diff(base)`(`{路径: A|M|D}`)、`snap.renames(base)`(`{新: 旧}`);清单不含 `.nomess/`。

<!-- >>> P22 -->
### 钩子管理器、停用、review-input(P22)

- **接入方式**(`githook.manager`,`githook.status` 的 `manager`):`native`(钩子文件自己写)、`husky`(`core.hooksPath` 指向 `.husky/_`:接入 = 用户脚本 `.husky/<钩子名>` 里有启动器的调用;`install` 不往 `.husky/_` 写任何东西,打出配方)、`framework`(钩子目录里的文件是 pre-commit 框架写的:接入 = `.pre-commit-config.yaml` 里有 `id: nomess`(pre-commit 阶段)和 `id: nomess-merge`(pre-merge-commit 阶段),`install` 打出两个本地 hook 的 YAML 和 `pre-commit install --hook-type pre-commit --hook-type pre-merge-commit`)。`hooks status` 逐项报。
- **hooksPath 范围**:钩子文件只调 `$(git rev-parse --git-common-dir)/nomess-hook`、不写本仓库路径,全局绝对 hooksPath 下也安全;相对 hooksPath 每个 worktree 各自解析,`doctor` 逐个 worktree 查并单独报没接的;`doctor` 报接入方式、钩子目录、启动器位置和 `.nomess/cache/` 大小。
- **停用**:`hooks uninstall` 只删内容和自己写的一致的钩子文件,启动器换成一行 `exit 0` 的存根(`githook.STUB_BODY`);存根就是主动卸载的记录:guard 不 deny 也不提示,`doctor` 报"已停用",`hooks install` 恢复。husky、框架的接线不动(启动器是存根时它们是空操作)。
- **review-input** `nomess review-input <基准> [片段文件]`:输出顺序固定:审查档(取全局 `review.level`)→ 必审(新增 `allow`、新冻结的规则号、被放宽的基线 / 配置;`cmd` 规则这里不执行,新冻结的 `cmd` 规则号的 B1 标"未执行,无法核对"、不当新违规)→ 新增红黄项(存量不列)→ 路径命中改动文件的教训标题 → diff → 片段文件原样。检查结果取 `evaluate(HEAD 树, 基准树, exec_cmd=False)`。加 `--cmd` 把审查清单和上面这份输入从标准输入交给 `review.cmd`(argv 数组,不经 shell)并打印它的输出;非零退出或超过 600 秒报错,不当"没发现问题"。
<!-- <<< P22 -->
<!-- >>> P23 -->

### P23 按文件的检测:缓存事实

模块 `clones.py`(D1、PL-DUP)和 `smells.py`(P1、P2、P5、S1、S2)。所有事实只取 `cache.facts`,`version` 都是模块里的常量 `ANALYZER`(改分词 / 提取逻辑就加一),分析器一变旧缓存整批作废。规则号:`clones` 出 D1(一字不差红、归一后相同黄,只比不同文件之间、不查文件内部,阈值取两边较小;一边关了 D1 另一边开着照报)和 PL-DUP(`docs/**/*.md`,黄);`smells` 出 P1、P2、P5、S1、S2。源码扩展名 = `deps.EXT_LANG` 加 `smells.extra_ext`。

**缓存存什么(`kind`,每个只含单个文件文本能得到的原始事实)**

| kind | 对象 | 存的事实 |
|---|---|---|
| `clones.tok.<家族>` | 源码文件 | 去注释和空白后的 token 数;两路 winnowing 指纹(`[哈希低 32 位, 第几个 token, 哈希, 序号, ...]` 交替排成 32 位无符号小端数组、整体 base64 编成一个字符串存,用到时才解码;`{"n": token 数, "x": 精确, "m": 归一}`;不存行号,行号命中后重新分词得到):**精确**(原样 token)和**归一**(标识符换占位、字面量保留类型);指纹用固定的 K=25、窗口 W=26(保证长度 ≥50 的重复必有共同指纹) |
| `clones.doc` | `docs/**/*.md` | 去掉生成段(用 `docgen` 现成的标记正则圈出)和代码块之后的 token 数和精确指纹,参数同上 |
| `smells.<语言>` | 源码文件 | 非空行数;P2 每个标签的出现数;P5 用的"定义的标识符"表;`py`:函数 `[全名, 起, 止]`、except 块 `[行, 抓的类型("全部"/"具体"), 处理体("吞"/"别的")]`;`js`:空 catch 的行号;`excepts` 里还存抓的类型文本供提示 |

`<家族>` 是注释写法的家族(`c`:`//` `/* */`;`hash`:`#`;`other`:不剥注释),`<语言>` 是 `py` / `js` / `other`。扩展名到家族 / 语言的映射写在代码里,映射的输入(`deps.EXT_LANG`、`smells.extra_ext`)不进缓存:同一文件换扩展名就是换 kind,所以改映射不会读到旧事实。

**什么不进缓存(每次现算)**

- 全部阈值(`clone_tokens`、`clone_lines`、`doc_clone_tokens`、`file_lines`、`func_lines`)、开关、颜色:判定在缓存之后做。指纹只保证 ≥50 个 token 的重复,所以 `clone_tokens` / `doc_clone_tokens` 小于 50 按配置错误退出 2(低了会漏报,不静默钳到 50)。
- 跨文件的结果:全树指纹索引、哪两个文件撞上、向两边扩到多长、是否一字不差,都从各文件缓存的指纹每次在内存里建;命中后只重读撞上的那几个文件做扩展。索引只为查询文件的指纹建;出现在超过 `COMMON`(10)个文件里的指纹当样板不当种子(否则 N 个结构相似的文件两两配对,耗时随 N 平方涨;照 MOSS 对公共 k-gram 的做法),所以复制到第 11 份以后的重复不报。
- 和基准 / HEAD 的比较:新增、`new` / `frozen` / `worse` 全由 check 按基线判;P2 是指标类(每文件标签总数)、P5 是次数类(`k` = 名字,文件名为 `@file`),"比基线多 / 新增"都落在这套基线上,检测器不看基准。
- 文件清单、`changes`、`eff(path)` 的有效配置。

<!-- <<< P23 -->
<!-- >>> P24 -->
### P24:`arch`(子系统间约束)、依赖图、系统图

- **模块 `arch`**(登记在 `DETECTORS`,`RELATIONS = True`):按图的检测,整棵树现算、不看 `changes`。没开 A1、`arch` 也没登记任何约束时只查 `systems` 重叠。
  - A1 子系统成环(tree 类,跟 `check.builtin`):依赖图按子系统收成有向图取强连通分量;只由 Python 边(源文件 `.py`,`ast` 取的 import)成的环红,含别的语言边的环黄(正则近似)。`file` `"-"`,`k` 排好序的成员。
  - A2 下层依赖上层(`arch.layers`,第 0 层最上,同层不查)、A3 声明独立的互相依赖(`arch.independent`,一组子系统名)、A4 点名禁止(`arch.forbid`: `{from, to, why}`):`select: edge`,每条文件依赖边一条发现,`file` 是源文件、`line` 是 import 行,`k = [from, to]`、`edge = (from, to)`;A2 / A3 的边落在环上填 `under = ("A1", 环成员)`(红环优先),A1 挡提交时不再逐边报。
  - `arch.relations` 两种 kind,规则号就是条目 `id`,颜色是条目的 `level`(原 A5 就是 `single_writer`,不另占号):`single_writer`(`table: 表.列`,可选 `owner`;同一 `表.列` 只许一条)每个值的写入行只能落在一个子系统、写了 `owner` 就必须是它,违规的每一行报一条;`needs`(`from` / `to: 表.列`,可选 `same_system`)`from` 的每个值 `to` 里也要有。`file` 是行所在文件,`line` 0,`k = [表.列, 值]`。表名不能含点(`表.列` 按第一个点分)。
  - `REL_EMPTY`(`freeze: False`):红色关系引用的表一行都没抽到,表上 `may_be_empty: true` 的除外;`file` 是 `nomess.json`。`UNOWNED`(黄,`freeze: False`,登记了约束才报):出现在依赖边或关系行里、但不属于任何子系统的文件条数。
  - 不属于任何子系统的文件不参与任何约束。`arch` 段写错(子系统名不存在、`表.列` 不存在、同列两条 `single_writer`、形状或多余的键)抛 `ValueError` 退出 2。
- **归属**:`map.owners_of(systems, 文件)` 是唯一入口(系统图和 `arch` 共用);一个文件匹配两个子系统 -> 退出 2 并报出文件。没填 `systems` 按源文件所在的顶层目录划。
- **生成器 `owners`**(`builtin: owners`):从 `single_writer` 出归属图的主人表,按 `表.列` 排序。
- **缓存事实**:`deps.<语言>`(`deps.VERSION`)= 每个文件还没解析的 import(Python `[点数, 模块, 名字, 行]`;JS / C / Go 字符串和行;Rust `mod` / `use`;C# 声明的命名空间和 `using`);`deps.header.py` / `deps.header.other`(`deps.VERSION`)= `[头注释第一句 | null, 文件是否为空]`(系统图文件清单和 HDR 用);`map.table`(version = 表名@表配置 sha1)= 每个文件的正则命中(各捕获组去首尾空白)。import 落到哪个文件(边)、子系统归属(`owners_of` 按 glob 的字面首段分桶再匹配)、行属于谁,每次现算。
- **依赖图**:`deps.edges(snap, files)` 返回 `{(源, 被依赖): 行}`。`EXT_LANG` 名字和结构不变。
- **系统图**:`size` 为 `small` 时只出 `index.md`(不带分页链接,热点行不链分页);`files.md`、`deps.md` 超 `map.page_tokens` 时 `files.md` 收成每个目录一行(文件数)、`deps.md` 只列跨子系统的边;依赖热点阈值读 `smells.fan_in`;热点清单末行"屎山存量 N"(`check.load_baseline` 的条目数);和已有页的比较走 `docgen.same`。
<!-- <<< P24 -->
<!-- >>> P25 -->
**plancheck**(`scripts/plancheck.py`,C4 和 PL-STALE;都是 tree 类,开关只看顶层 `check.builtin`,两个检测器各看各的开关,关了的不跑,大项目缺省开):

- **C4**(读 `<docs_root>/schedule.md`,列 `包` / `依赖` / `状态` / `可改文件`,没有“可改文件”列的表不查;可改文件用逗号、顿号、分号或空格隔开的 glob):两个“在做”包重叠红(有依赖也报);“在做”的包依赖的包不是“已合”红;两个“待派”包重叠黄;其余状态组合不查。红只给确定的重叠:有现存文件同时匹配两边,或两边有不带通配符的字面路径完全相同(花括号先展开);只凭 glob 第一个通配符之前的字面前缀推断的重叠(都要新建的路径也算;`src/a/**` 和 `src/ab.py` 不重叠,`src/*.py` 和 `src/*.js` 前缀相同只算黄)一律黄,“在做”也是。排期里列数不对或状态值不认识的行、依赖里不在排期的包名各报一条黄(`k = ["row", 行号]` / `[包, 依赖, "nodep"]`)。`file` 是排期表、`k = [包A, 包B, 重叠路径]`(两个包名排好序;重叠路径 = 现存的重叠文件取排序第一个,否则取更长的字面前缀);依赖未合的 `k = [包, 依赖, ""]`。
- **PL-STALE**(黄):`<docs_root>/plans/` 下不在 `archive/` 的方案,正文里反引号中带斜杠、末段有扩展名的路径(跳过代码围栏,去掉 `:行号` 后缀)不存在,或方案头 `系统:` 的名字不在 `systems` 里。没写 `系统:` 的只按路径查。`k` 缺省 `[路径]` / `[system:名字]`。
- 无缓存事实、无配置键。提示语键前缀 `PC_`。
<!-- <<< P25 -->
