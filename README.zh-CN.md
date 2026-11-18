<p align="center"><img src="docs/logo.svg" width="96" alt="nomess logo"></p>

# nomess

[English](README.md) | 简体中文

nomess 是一个 Claude Code 插件，让多个 AI 长期改同一个仓库时代码不乱、少返工。它有六个部分：动手前先查的写代码方式、先设计后派活的流程和提交闸门、从代码生成的系统图、记忆与教训、按路径加载的规则、屎山特征检测。提交检查是 git 钩子里的 Python 脚本，不调用模型，不花 token；整个插件只需要 Python 3.9 和 git。

## 30 秒上手

```sh
claude plugin install nomess --marketplace penstic123-code/Nomess
```

这一条命令把 GitHub 仓库加为插件源并装上插件（在 Claude Code 里是 `/plugin install nomess --marketplace penstic123-code/Nomess`）。安装时会问一次用哪个 Python 命令：macOS / Linux 用 `python3`，Windows 用 `python`（只有 `py` 就选 `py`）。加 `--config python=python3` 可以跳过这个问题；以后在 `/config` 里改。

然后在项目里打开 Claude Code，运行 `/nomess:init`（它要提问，所以要在交互会话里跑；`claude -p` 没法回答）。它会问项目规模和文档语言（`en` 或 `zh-CN`），找出（或问你）主分支，装上 git 钩子，把现有问题冻结成基线，最后给一份报告：存量问题、钩子装在哪、一段 CI 配置。它从不覆盖已有文件。项目里多出：

```
nomess.json            设置和检查规则
AGENTS.md              入口，含生成的 nomess 段（CLAUDE.md 第一行加 @AGENTS.md）
docs/overview.md       设计总览，给人看
docs/systems/*.md      每个子系统一页（"细节"和"坑"两段要你自己补）
docs/lessons/          教训库
docs/system-map/       生成的，别手改
.nomess-baseline.json  现有问题的基线，之后只有新问题才挡
.nomess/               本地缓存，已被 git 忽略
```

大项目还会多 `docs/schedule.md`、`docs/ownership-map.md` 和 `docs/plans/`。`.gitignore` 加一行，`.gitattributes` 加三行。

装了没反应？跑 `nomess doctor`：一项一行，每个问题都带修法。

## 日常是什么样

装好插件后，在项目的 Claude Code 交互会话里跑 `/nomess:init`，选规模、文档语言和主分支，接上提交检查。平时照常改代码、暂存和提交。假如代理把一段够长的校验代码复制到另一个文件，提交会停下来。提示会像这样，指出两段代码在哪儿：

```text
nomess: 1 条新红项,首条 src/import.py:42 D1 src/import.py 第 42-58 行和 src/validate.py 第 10-26 行重复(108 个 token,一字不差);详情跑 nomess check --red
```

代理可以沿着提示读两处代码，让导入流程调用已有校验，再暂存、提交。通过时通常没有输出。下文的 `/nomess:…` 是在 Claude Code 里输入的命令，`nomess …` 是脚本命令。在自己的终端里也能用 `python <插件安装路径>/scripts/nomess.py` 加上同样的参数来跑。

## 1. 少写代码，动手前先查

假设两个上传入口都把空文件名保存成了空字符串。代理只看到其中一份报错，就容易给那个入口补一个判断。第三个入口一出现，同样的 bug 还会回来。`lean-change` 要代理先找调用者，顺着数据走一遍，弄清楚哪个共享环节该负责校验。

`lean-change` 是一个 skill，也就是 Claude Code 可以在相关任务中加载的一份工作说明。写功能、修 bug、重构或选依赖时，它会被加载。你可以照常描述任务。代理会先找改动涉及的调用者、数据、配置和文档，读要改的文件，再用 `nomess lessons find <路径或关键词>` 查最多三条相关教训。

接下来有一套有顺序的问题。这个功能有必要做吗？仓库里已经有了吗？标准库或已安装的依赖能解决吗？碰上协议、并发或不熟悉的第三方接口，先查可靠资料。前面都走不通，再写足以解决问题的代码。交付时，代理说明自己停在哪一步、用什么验证了改动。

这套顺序比一句“尽量少写代码”更具体。找到共享校验层，可能要改两个调用点，但两个入口从此走同一套逻辑。只压缩 diff，反倒容易把判断留在错误的位置。

## 2. 防屎山流程和提交闸门

给存档加一个字段时，如果一个代理改写入格式，另一个同时给读档补默认值，两份代码各自都能通过测试，合起来却可能把旧存档里的值覆盖掉。`workflow` 管这种需要几个人先说清楚的事。提交闸门管另一类问题，比如某个模块里出现了项目明确禁止的调用。

Claude 规划、派活、审查或合并时会加载 `workflow`。注释和文档之类的小改动可以直接做，单点修复走轻流程。改接口、存档格式、执行时序或数据归属时走全套流程。先定谁读、谁写、什么时候写，再评方案。派活前让一个没参与讨论的子代理试读简报，看看只凭这份材料还缺什么。并行任务各用一个 Git worktree，也就是同一仓库的独立工作目录。手动审查已提交的改动用 `/nomess:review`。

闸门由 Git 调用。`pre-commit` 在普通提交落盘前跑，`pre-merge-commit` 在 Git 自动创建合并提交前跑。脚本读取暂存区里将要提交的文件、配置和基线，以 `HEAD` 的树作为比较起点。用 `git add -p` 只暂存了半个改动，内置检查就按那半个改动组成的文件版本来判断。项目自己登记的 `cmd` 检查读磁盘，发现已跟踪文件还有未暂存改动时，钩子会跳过它并提示交给 CI。

项目规则写在 `check.rules`。`forbid` 查禁止出现的模式，`require` 查文件里必须存在的模式，`cmd` 用项目命令的退出码判断。红项会挡，黄项供人查看。某个文件确实需要例外时，可以在顶层 `allow` 里写清规则、文件和理由。新增例外会出现在审查输入里。

把检查交给 Git，人在终端提交时也会跑，整个过程无需调用模型。人可以用 `git commit --no-verify` 应急。Claude Code 的插件钩子会在执行常见 shell 命令前拦截代理使用这个选项或改 `core.hooksPath` 来绕过检查。团队还可以在 CI 跑 `nomess check --ci --base <可信提交>`，用 PR 的目标提交对比 `HEAD`。项目有意放宽规则时，由人批准，给 PR 加 `nomess-loosen` 标签，并让 CI 据此传 `--allow-loosen`。

## 3. 系统图和自动更新的文档

准备拆掉 `billing` 前，你想知道哪些模块还在导入它。手写架构图最擅长解释为什么这么分，半年后却很难靠它确认还有谁在调用。`docs/system-map/index.md` 给你一个从代码生成的入口。项目规模较大时，还有文件表、依赖表和自定义抽取表。

运行 `nomess map` 可以手动重建系统图。脚本从 Git 的文件清单出发，按 `systems` 配置给文件分组，没配就按源码的顶层目录分。它把能解析到仓库文件的导入关系连成边，再汇总到子系统之间。Python 用语法树提取导入，部分其他语言用文本模式近似。项目也能用 `map` 里的正则抽取约定统一的内容，例如把 `EMIT("order.paid")` 这样的调用汇成事件表。动态拼出来的事件名超出了这张表的视野。

要把事件表放进手写文档，可以在 `docgen` 里登记一个叫 `events` 的生成段，并在文档里放两行标记：

```markdown
<!-- GEN:events BEGIN -->
<!-- GEN:events END -->
```

`nomess docgen` 只替换两行之间的内容。主分支上符合条件的普通提交会自动刷新系统图、规则文件和可从快照生成的文档段。钩子先把生成结果叠到候选提交上一起检查，通过后才写进这次提交。带未暂存编辑的生成目标会跳过，`cmd` 和 `py` 生成器留给手动刷新。自动合并的钩子只检查，功能分支上的生成物也可能落后，想更新可以跑 `nomess refresh`。

这样维护文档时，人写设计取舍和踩过的坑，脚本重算能从代码里得到的清单。改了一处导入，无需再凭记忆去给另一张图补一根线。

## 4. 记忆与教训

一次故障修完后，Git 能告诉你哪几行改了，却很难告诉下一个人，为什么上次给结算请求加重试会重复扣款。这种信息适合留在仓库里，和代码一起供后来的人查。

用 `/nomess:lesson "结算重试必须复用原请求的幂等键"` 记一条。插件会整理出标题、什么时候该查这条教训，以及该怎么做、为什么、依据是什么。脚本给它加日期，写进 `docs/lessons/inbox.md`。同标题会更新原条目，旧说法可以从 Git 历史里找。没拿代码核实的条目会标成未核实。`lessons find` 用路径和关键词查这些条目，所以适用场景里写上 `src/billing/` 和“重试”，比只写“结算有坑”更好找。

条目积多了，跑 `/nomess:dream`。它先检查教训库，以及能定位到的当前项目的 Claude Code 记忆目录，找重复标题、断链、超预算的页面，再用代码和 Git 历史核对提案里的事实。你看过提案后，用 `/nomess:dream execute` 执行，也可以用 `execute strike 2 5` 划掉第 2、5 项。整理会合并重复、清掉过期说法，并提议把反复有用的教训变成规则。执行后会校验结果，并在可提交的仓库里留下记录。

这批内容是普通 Markdown，短、能审 diff、可以跟着分支走。对“改结算重试前查哪条教训”这种问题，路径和关键词已经能把范围缩得很小，没必要再维护一套向量库。用词不同的同义教训则有可能搜不到。

## 5. 按路径加载的规则

“结算重试沿用原幂等键”对 `src/billing/` 很重要。只改首页样式的代理读到它，除了多占一点上下文，几乎用不上。把所有教训都塞进项目入口，最后连真正通用的规矩也难找。

`dream` 可以提议把一条反复适用、已经核实的教训升成路径规则。你也可以在系统说明页的“坑”里写一条。源条目要有已核实状态、路径模式和一句规则，`inbox.md` 里的草稿不会生成。运行 `nomess rules` 后，路径集合相同的条目会进同一个文件，放在 `.claude/rules/nomess/`。文件名取这组路径的哈希，文件头里的 `paths` 告诉 Claude Code 什么时候加载它：

```yaml
---
paths:
  - "src/billing/**"
---
```

Claude Code 读取命中路径的文件时才加载这份规则。只搜到了几行 `grep` 结果，还得打开文件让规则进入上下文。每条规则后都带源条目链接，短句不够用时可以回去读完整原因。

路径规则适合需要判断的约定，比如“这次重试该沿用哪个请求的键”。如果要求是“结算代码里只允许某个模块调用底层写入函数”，这类能判定的限制可以交给提交检查，每次按同一个条件执行。

## 6. 屎山特征检测和棘轮

老仓库里已经有三段重复代码时，一装工具就要求清完，连改个小 bug 都得先还旧债。完全放过存量又会让第四段、第五段悄悄进去。nomess 在初始化时先用 `nomess check --freeze` 把现有发现写进 `.nomess-baseline.json`，之后拿这份清单判断哪些问题是新增的、哪些长大了。`nomess check --rules` 可以看规则说明，`nomess check --all` 能展开存量。

| 检测项 | 脚本看什么 |
| --- | --- |
| D1 代码重复 | 跨文件有够长的一段代码词元完全相同报红，归一化后才相同报黄。 |
| P1 吞异常 | Python 用语法树找捕获范围和处理体。捕获全部异常后只写 `pass` 等空操作报红，吞具体异常或 JS/TS 空 `catch` 报黄。 |
| P2、P5 补丁痕迹 | 数 `TODO`、`hack` 等标记，找 `_v2`、`_old` 一类的文件名或定义名，报黄。 |
| S1、S2 长度 | 数文件非空行，或用 Python 语法树取函数起止行。越过配置上限的新增或恶化项可报红。 |
| A1 与 `arch` 架构约束 | 把导入边汇成子系统图。仅由 Python 导入边构成的环报红，依赖近似提取才成立的环报黄。项目还可登记禁止的依赖方向、单一写入归属等约束。 |
| C4 并行排期 | 两个在做的任务确定会改同一文件，或一个任务开工时前置任务还没合入，报红。只从通配符前缀推测重叠时报黄。 |
| PL-DUP、PL-STALE 文档 | 文档间重复的文字、未归档方案里失效的路径或子系统名，报黄。 |

D1 不必把每个文件的全文两两比较。它先去掉空白和能识别的注释，把代码切成词元。每 25 个连续词元算一个哈希，再从滑过的每组 26 个哈希里挑最小值当指纹。两个文件撞上指纹时，脚本回到原词元，向两端扩展并核对，确认实际重复了多长。一路保留原词元，一路把标识符和字面量按类型归一，所以改了变量名的副本也有机会被发现。出现在太多文件里的常见指纹会被略过，避免样板代码拖慢所有提交。

基线用规则号、原始颜色、路径和问题自身的特征来识别发现，行号只用于提示。比如某文件已经冻结了两处 P1 红项，多出第三处才算新红项。长度一类的指标会和冻结时的数值比，增长超出配置的容忍幅度才算恶化。修完旧问题后，可以跑 `nomess check --tighten` 删掉消失的条目、压低已有数值。额度收回后，同样的问题再出现就得重新面对检查，这就是棘轮。

B1 防止把问题藏进基线。已有规则的额度不能靠手改文件增加。首次冻结只给基准中还没启用、这次确实执行过且允许冻结的规则，记录也得能在本次全量扫描里对上。B2 防止改尺子。它比较两边展开默认值后的配置，删检查、抬高受管阈值、降低审查档、换基线位置或删掉 `nomess.json` 都会触发。冻结把接入成本留在可接受的范围内，B1 和 B2 让同一份改动不能顺手把防线挪走。

## 六个部分怎么配合

假设结算和后台补偿各写了一次账本。你修完故障，用 `/nomess:lesson` 留下当时的原因和两个入口。`dream` 核对后发现，两条经验适合用不同方式留下。一条是“重试时沿用原请求的幂等键”，需要代理读上下文判断，生成到结算目录的路径规则里。另一条是“只有账本模块能调用底层写入函数”，可以登记成红色 `forbid` 规则，并给合法写入文件留一个有理由的例外。

后来有人让 AI 加批量补偿。`lean-change` 让它先找原有写入口，读文件时路径规则提醒它保留幂等键。系统图能帮它找到结算和账本之间的依赖。假如批量补偿还要改写入归属，`workflow` 会让协调者在派活前把谁写账本定下来。即使代理漏了前面的提醒，暂存的新文件只要在禁止范围内直接调用了底层写入函数，Git 钩子就会按新规则挡住提交。

## 适配大小项目和怎么自己调

`size` 给的是一组缺省值。一个人、一次一个代理，从 `small` 开始就行。它开 D1、P1、S1，审查用 `light`。几个代理开始并行时，`medium` 加 A1，审查升到 `standard`。`large` 再加 C4、PL-DUP、PL-STALE，还用排期表列任务和可改文件，用归属图记录共享数据由谁负责。

这份配置保留中档的四项检查，给手写支付代码加上函数长度检查，并把涉及这些文件的审查提到 `strict`：

```json
{
  "format": "nomess/1",
  "main_branch": "main",
  "size": "medium",
  "lang": "zh-CN",
  "check": { "builtin": ["D1", "P1", "S1", "A1"] },
  "scopes": [
    {
      "paths": ["src/payments/**"],
      "why": "支付改动需要逐项审查",
      "checks": { "add": ["S2"] },
      "smells": { "func_lines": 60 },
      "review": "strict"
    }
  ]
}
```

`check.builtin` 是显式清单，写了就接管规模的默认开关。`scopes` 可以按路径加减单项文件检查、调颜色和阈值，也可以改审查档。多个范围命中时，更具体的路径逐项覆盖。A1、C4 这类看整棵树的检查由顶层设置控制。

审查的 `off` 完全关闭审查。`light` 通常只审合批后的改动，跳过文档、配置和测试。`standard` 还会审单包的逻辑代码，`strict` 则每包都审。启用审查时，全套流程、超出简报的改动和新增例外等会单独进入必审判断。一个改动碰到多个目录时，取其中最严的档。项目 `AGENTS.md` 或 `CLAUDE.md` 已经规定了怎么试读、测试或审查，就按项目的规矩走。

`nomess status --suggest` 会列出升降档的依据，比如近期合并与文件重叠、子系统数量、积压的教训，或一段时间里只有一位作者且没有并行合并。建议由人决定是否采纳。升档可以重跑 `/nomess:init`，配有显式开关时也要看一眼清单。降档如果关掉了检查或降低了审查档，就走项目批准放宽的流程。

## 它不做什么

提交闸门是工作约定，安全边界得由权限和受保护的 CI 提供。新克隆要接上本地钩子，快进合并、rebase、cherry-pick 也不能指望本地钩子兜底。

系统图能从代码提取清单，设计理由和取舍得由项目团队写。nomess 的本地脚本不联网、不做遥测，提交检查也不调用模型。`dream` 和审查在 Claude Code 会话里做，`nomess.json` 里登记的自定义命令则会按配置执行。
## 日常使用

| | |
|---|---|
| `/nomess:lesson "<一句话>"` | 把教训记进 `docs/lessons/inbox.md` |
| `/nomess:dream` | 出提案：合并重复、删过期、把验证过的教训变成规则；`/nomess:dream execute` 执行 |
| `/nomess:review` | 按 `nomess.json` 的 `review.level` 审当前改动 |
| `nomess check` / `nomess map` | 手动跑检查 / 重新生成系统图 |

自己的规则写在 `check.rules`：`forbid` 报匹配正则的行，`require` 报没有匹配的文件，`cmd` 非零退出就报；`red` 挡提交，`yellow` 只报告。正则写在 JSON 字符串里，`\b` 要写成 `\\b`。全部键见 [`nomess/scripts/README.md`](nomess/scripts/README.md)。

```json
"check": { "rules": [
  {"id": "R1", "level": "red", "what": "no print() in src", "why": "use the logger", "glob": "src/**/*.py", "forbid": "\\bprint\\("}
]}
```

### 在你自己的终端里用 `nomess`

`nomess` 只在 Claude 的 shell 的 PATH 上。在你自己的终端里直接跑脚本：`python <安装路径>/scripts/nomess.py check`（`<安装路径>` 是 `claude plugin list --json` 输出里的 `installPath`；`nomess doctor` 也会打出各处位置）。本文里写成 `nomess ...` 的命令都这样跑。

### 提交被挡时

```
nomess: 1 new red finding(s), first src/a.py:1 R1 prevents: use the logger; details: nomess check --red
```

这是规则在起作用，不是程序崩了（有的工具会在前面加"hook failed"）。读法：文件:行、规则号、这条规则防什么。跑 `nomess check` 看完整清单，改代码，再提交。init 时冻结的存量问题不挡，只有新问题挡。规则对某个文件确实不合适，就在 `nomess.json` 顶层 `allow` 里加一条并写理由；审查必须看每一条新增的 `allow`。

急用时，人可以用 `git commit --no-verify` 跳过检查（代理这么做会被插件拒绝）。放宽规则本身（删规则、把正则改窄、删 `nomess.json`）也要 `--no-verify`，并在 PR 上打 `nomess-loosen` 标签；没有标签 CI 会红。

## 它不是安全边界

git 钩子是减速带。`--no-verify` 能跳过；cherry-pick、rebase、am 不保证被检查；没跑过 init 的克隆没有钩子；同一个工作区不支持几个代理同时提交（并行的代理各用一个 worktree）。CI 是兜底，把下面这段放进 `.github/workflows/nomess.yml`：

```yaml
name: nomess
on: [pull_request, push]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: git clone --depth 1 --branch v0.9.1 https://github.com/penstic123-code/Nomess ../nomess-src
      - env:
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
          LOOSEN: ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
        run: python ../nomess-src/nomess/scripts/nomess.py check --ci --base "$BASE" $LOOSEN
```

`BASE` 必须是可信的提交：PR 的 base，或 push 的 `before`。新分支第一次 push 时 `before` 全是 0，改用和主分支的 merge-base。

## 要求

Claude Code 2.1.277 或更新，Python 3.9+，git 2.24+。适合中小仓库：源文件上千个的仓库，目前提交时检查要几秒（更快的缓存计划在 0.9.1）。`/nomess:init`、`/nomess:lesson`、`/nomess:dream` 和代理提交都通过 Claude 的 shell 工具跑脚本，所以这个工具得能用。

## token 开销

- **常驻约 530 token。** 两个 skill 和两个子代理的简介约 280（用 `claude plugin details nomess` 核对），`AGENTS.md` 里的 nomess 段（不超过 12 行）约 250。`/nomess:init` 这类手动命令不运行就不花。
- **每个写代码的上下文多约 2,000**（`lean-change` skill 正文）。这是小项目的主要开销。规则文件只在打开匹配文件时加载，每份不超过 400。
- **钩子：0。** 它们是脚本。被挡一次的提交会在代理面前多约 60 token 的输出。
- **一次 `/nomess:dream`：** 普通的 Claude 会话，在 19 页记忆目录上实测约 9.5 万 token（提案约 4.7 万，执行约 4.9 万）。

## 读写范围

项目里：`nomess.json`、上面列的生成文件、`.gitignore` 一行、`.gitattributes` 三行、`.nomess/`；`.git/` 里两个钩子文件和一个启动器（`.git/nomess-hook`），都不进版本库。项目外：Python 选项，由 Claude Code 存在 `~/.claude/settings.json`；你添加的插件源声明在用户设置里；`/nomess:dream` 在你确认后改 Claude Code 的记忆目录，必要时在那里 `git init` 并提交（不推送）。它读 `autoMemoryDirectory` 设置。它不碰 `~/.claude/CLAUDE.md`，不建 `~/.claude/memory/`，不读别的项目。

子代理：`reviewer` 和 `trial-reader` 是"按指示只读"；它们的工具表含 shell（要跑 `nomess` 和 git 看 diff），所以这是写在提示词里的规矩，不是沙箱。

## 安全和隐私

不联网，不做遥测，不收集数据。**`nomess.json` 里登记的命令会被执行**：`cmd` 检查规则和 `cmd` / `py` 文档生成器在提交时和 `nomess check` 时运行；`review.cmd` 在 `/nomess:review` 时运行。把 `nomess.json` 当构建脚本对待，在别人写的仓库里干活前先读一遍；`nomess check --no-exec` 会跳过它们。

## 怎么关掉、卸载

- **只停 Claude Code 里的部分：** `/plugin disable nomess`。git 钩子照跑。
- **本机停用提交闸门：** `nomess hooks uninstall`（删掉它写的钩子文件，启动器变成空操作；`nomess hooks install` 可恢复；要彻底清除再删 `.git/nomess-hook`）。`nomess hooks status` 看当前状态。
- **仓库不再用 nomess：** 提交里删掉 `nomess.json`。这算放宽，要打 PR 标签 `nomess-loosen`。之后可以删的文件：`.nomess-baseline.json`、`docs/system-map/`、`docs/lessons/`、`docs/systems/`、`docs/overview.md`（以及大项目多出的文件）、`.claude/rules/nomess/`、`AGENTS.md` 里的 nomess 段（两个标记之间）、`CLAUDE.md` 第一行的 `@AGENTS.md`、`.gitignore` 里的 `.nomess/` 一行、`.gitattributes` 的三行、CI 文件。
- **卸载插件：** `claude plugin uninstall nomess`，再 `claude plugin marketplace remove <插件源名>`（名字见 `claude plugin marketplace list`）。

## VS Code 扩展

侧栏看文档，检查结果显示在问题面板，状态栏显示过时文档数。它调用同一个脚本，从不调用 Claude。商店版即将上架，在那之前可从源码构建。

## 更多

[更新记录](CHANGELOG.md) · [许可证：MIT](LICENSE) · skill 原文：[`nomess/skills/`](nomess/skills/) · 中文译文：[`docs/zh-CN/`](docs/zh-CN/) · 问题和 bug：GitHub Issues，仓库 `penstic123-code/Nomess`。个人维护的项目，不承诺响应时间。

致谢：思路来自 [ponytail](https://github.com/DietrichGebert/ponytail) 和 Google 的 [ReasoningBank](https://github.com/google-research/reasoning-bank)；没有拷贝代码。

