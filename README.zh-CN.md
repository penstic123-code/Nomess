# nomess

[English](README.md) | 简体中文

**多个 AI 代理改同一个仓库时，nomess 让它们守住项目自己写下的规矩：每次提交都有检查，按目录加载的教训由代理自己想起，先设计后派活的流程带审查档位。** 这是一个 Claude Code 插件，只需要 Python 3.9+ 和 git。

## 装上得到什么

- **提交时自动检查，零 token。** git 钩子（`pre-commit`、`pre-merge-commit`）跑你的规则（正则规则或你自己的脚本），再加能确定判断的内置检测（见"选规模"）。人在终端里提交也会检查。没问题不出声；出现新问题就挡下这次提交，只给一行提示。
- **碰到哪个目录，代理就想起那个目录的坑。** 用 `/nomess:lesson` 记下的教训可以变成按路径加载的规则文件（`.claude/rules/nomess/`；由 `/nomess:dream` 提议、你批准），Claude Code 只在打开匹配的文件时才加载。
- **从代码生成的系统图。** `docs/system-map/` 在主分支（`nomess.json` 的 `main_branch`）的提交里一起刷新；功能分支上可能过时。
- **先设计后派活的流程。** Claude 规划、派活或合并时，`workflow` skill 加载：改动分三档（全套 / 轻流程 / 直接改），简报细到能直接交给子代理，派活前先试读，审查分三档（`light` / `standard` / `strict`）。
- **能读、能改、能进 git 的教训和记忆。** 都是 markdown；`/nomess:dream` 先出提案，你确认后才整理。

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

### 选规模

`nomess.json` 的 `size` 决定缺省开哪些内置检测、用哪档审查。选够用的最小一档；你在 `check.builtin` 或 `review.level` 里写了的，以写的为准。

| `size` | 适合 | 开的内置检测 | 审查 |
|---|---|---|---|
| `small` | 一个人、一次一个代理 | D1 一字不差的复制粘贴（红）、P1 吞掉全部异常（红）、S1 新文件超过长度上限（红） | `light` |
| `medium` | 几个代理、有些并行 | 加 A1 子系统 import 成环（Python 边成的环才红） | `standard` |
| `large` | 很多代理并行 | 再加 C4 `docs/schedule.md` 里在做的包文件重叠、PL-DUP、PL-STALE | `standard` |

只有确定的情况才挡提交；改了名字的克隆、只吞一种异常、别的语言的环只报黄。要升档就重跑 `/nomess:init`；降档算放宽（见下）。`nomess check --rules` 列出每条规则查什么、防什么。

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
      - run: git clone --depth 1 --branch v0.9.0 https://github.com/penstic123-code/Nomess ../nomess-src
      - env:
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
          LOOSEN: ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
        run: python ../nomess-src/nomess/scripts/nomess.py check --ci --base "$BASE" $LOOSEN
```

`BASE` 必须是可信的提交：PR 的 base，或 push 的 `before`。新分支第一次 push 时 `before` 全是 0，改用和主分支的 merge-base。

## 和别的工具有什么不同

多数代理记忆工具给代理接一个自己会记录的外部大脑，背后是数据库、后台进程、模型调用或账号。nomess 的记忆是仓库里的 markdown，钩子从不调用模型，管的也不只是记忆。

| | nomess | [claude-mem](https://github.com/thedotmack/claude-mem) | [engram](https://github.com/Gentleman-Programming/engram) | [mem0](https://github.com/mem0ai/mem0) |
|---|---|---|---|---|
| 存储 | 仓库里的 markdown | SQLite + Chroma | SQLite + FTS5 | 向量库 |
| 怎么跑 | 提交时的脚本 | 后台进程；模型压缩每次工具调用 | 带 MCP 工具的单个程序 | 库或服务；LLM 抽取记忆 |
| 需要 | Python、git | Bun、uv、模型来源 | 无额外依赖 | LLM 和嵌入的密钥 |
| 还管 | 提交检查、系统图、流程、审查 | – | – | – |

已知短板：教训检索是关键词匹配，可能漏同义词；nomess 从不自动抽取记忆；函数级检测只支持 Python。

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

