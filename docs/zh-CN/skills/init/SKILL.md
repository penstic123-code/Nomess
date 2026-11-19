---
name: init
description: >-
  在本仓库启用 nomess，或升到更大的档：跑 `nomess init --auto` 并报告它做了什么。
disable-model-invocation: true
argument-hint: "[--size small|medium|large] [--lang en|zh-CN] [--docs standard|free|custom]"
---

# init：启用 nomess

下面的 `nomess` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`，在项目根目录运行。平时什么都不用做：会话钩子会让 AI 在第一次改文件前跑同一条命令。

1. 跑 `nomess init --auto --lang <en|zh-CN> [--size <档>] [--docs <文档管法>]`。还没有 `nomess.json`、`$ARGUMENTS` 也没写 `--docs` 时，先用一句话问用户文档怎么管：标准 7 类（`standard`）、不管位置，适合实验项目（`free`）、按项目定类型（`custom`：init 之后 AI 照项目提一套，用户点头再写进去；命令输出里写了怎么做）；用户不在意就 `standard`。已启用的项目不问。`--lang` 取用户说话用的语言；`$ARGUMENTS` 写了档才传 `--size`（缺省 `small`；按同时改代码的 AI 有几个：一个 → `small`，偶尔两三个 → `medium`，多数日子好几个 → `large`）。它什么都不问，只补缺的（重跑无害），不提交。
2. 退出 2：报告它的提示。分离头指针 → 问用户主分支，切到分支后重跑。不是 git 仓库 → 停（检查和钩子要 git；不替用户 `git init`）。`--size` 比现在小 → 要人来做：改 `nomess.json` 的 `size`，用 `--no-verify` 提交，PR 打 `nomess-loosen` 标签；降到 `small` 前，把指向系统图分页的链接改指 `index.md`（`small` 会删掉分页）。
3. 用一两句话把它最后一行转告用户：改了哪些文件、冻结了多少存量、提交检查接上没有（没接上时 `nomess hooks install` 会打出对应钩子管理器的配方）。换了档还要说现在生效的检查（`nomess check --rules` 里没标"未启用"的行；medium 加 A1，large 加 C4、PL-DUP、PL-STALE）。在这个仓库关掉 nomess：`nomess off`。

可以建议的下一步：在 `check.rules` 里登记"唯一入口"规则并配 `allow`，在 `scopes` 里按目录定严格程度（格式见 `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`）；以及 CI，`.github/workflows/nomess.yml`，填好主分支：

```yaml
name: nomess
on: [push, pull_request]
jobs:
  nomess:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - run: git clone --depth 1 https://github.com/penstic123-code/Nomess "$RUNNER_TEMP/nomess"
      - run: |
          base="${{ github.event.pull_request.base.sha || github.event.before }}"
          case "$base" in ""|0000000000000000000000000000000000000000) base=$(git merge-base origin/<main_branch> HEAD);; esac
          python3 "$RUNNER_TEMP/nomess/nomess/scripts/nomess.py" check --ci --base "$base" ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
```
