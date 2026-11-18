---
name: init
description: >-
  给项目搭 nomess 骨架，或升到更大的档：先问大小和语言，建 nomess.json 和 AGENTS.md 入口，装 git 钩子，生成系统图。
disable-model-invocation: true
---

# init：给项目搭骨架

模板在 `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/`（`en` 或 `zh-CN`），全是数据。下文的 `nomess.py` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`，在项目根执行。已存在的文件一律不覆盖，对已有文件只做下文写明的改动。跳过的文件要报给用户。

## 1. 先问清，一次问完

**大小**：只问一个问题："同一时间有几个 AI 在改代码？"窗口和子代理都算；按每月至少发生一次的情况答，不按平时。

| 回答 | `size` |
|---|---|
| 只有一个，从不并行 | `small` |
| 偶尔两三个并行（例如子代理跑几周的活） | `medium` |
| 多数日子有好几个（几个窗口，或一直在并行派包） | `large` |

**重跑**（已有 `nomess.json`）：只问大小，其余都从它读，然后跳到第 4 节。

- **文档语言**：`en` 或 `zh-CN`，写进 `lang`；它决定用哪个模板目录。
- **git**：`git rev-parse --show-toplevel` 失败就问要不要 `git init`；不要就停（检查和钩子都靠 git）。
- **主分支**（`main_branch`，不猜）：`git symbolic-ref --short refs/remotes/origin/HEAD` 去掉开头的 `origin/`；没有的话，如果还没有任何提交，用 `git symbolic-ref --short HEAD`；再不行就问。
- **项目名**：仓库根目录名，用作 `AGENTS.md` 的标题。
- **子系统**：读顶层目录和入口文件，列出名字和路径 glob（一个文件只能匹配一个）。空项目或看不出来，就问（只有一块也行）。

## 2. 建文件

每个大小都一样：`nomess.json`、`AGENTS.md` + `CLAUDE.md`、`.gitignore`、`.gitattributes`；系统图 `docs/system-map/` 是生成的（small：只有首页）。其余现在都不建：`docs/overview.md`、每个子系统的说明页、教训库、`docs/plans/`、`docs/schedule.md`、`docs/ownership-map.md`，第一次用到时才照模板建（`/nomess:lesson` 自己建 inbox；方案、排期、归属表由 `workflow` skill 建）。

1. `nomess.json`：拷模板；填 `main_branch`、`size`、`lang`、`systems`。不要写 `check.builtin` 和 `review.level`：它们跟着 `size` 走。
2. `AGENTS.md`：没有就新建 → `# <项目名>`、空一行，再接 `AGENTS-nomess.md`；已有 → 空一行后把 `AGENTS-nomess.md` 的内容追加到末尾（已有 `## nomess` 段就按标记规则处理）。`CLAUDE.md`：没有就新建，只有一行 `@AGENTS.md`；已有但没有单独一行这个 → 把它插在第一行。
3. `.gitignore`：没有就加一行 `.nomess/`。`.gitattributes`：下面三行缺哪行补哪行（一行一个模式）：`docs/system-map/** text eol=lf`、`.claude/rules/nomess/** text eol=lf`、`<lessons_dir>/inbox.md merge=union`（`lessons_dir` 缺省 `docs/lessons`）。

**标记规则**（每个 `docgen` 项）：`docgen` 只重写该项文件里恰好一对 `<!-- GEN:<key> BEGIN -->` / `<!-- GEN:<key> END -->` 之间的内容。目标文件已存在时：恰有一对 → 登记；没有 → 在末尾追加模板里的块（`nomess` 项是 `## nomess` 标题加这对标记）再登记；多于一对，或用户不让改 → 不登记，报告。

## 3. 收尾

1. `nomess.py refresh`（生成段、系统图、路径规则）。
2. `nomess.py check --freeze`：已有的欠账进 `.nomess-baseline.json`，所以第一次 check 没有红。
3. 再跑一次 `nomess.py refresh`（系统图首页要统计冻结的条目）。
4. `nomess.py hooks install`：保留它的输出（启动器、钩子目录，或已有钩子管理器的接入办法）。
5. `nomess.py check` 无红，`nomess.py doctor` 无 FAIL。红项在 init 建的文件里：改掉；在别处：报告。doctor 有 init 修不了的 FAIL（Python、插件的 python 选项）：连同它的 `Fix:` 行报告。

不提交。给用户报：
- 大小和语言；新建了什么；跳过了什么（已存在的）；占位符在哪；
- 已有欠账：`.nomess-baseline.json` 里按规则 id 的条目数，例如"copy-paste 3、吞异常 2，已冻结"；
- 钩子：`hooks install` 的输出；如果打印的是接入办法，用户接好之前提交不受闸门管；
- 下面的 CI 片段（填好主分支），放进 `.github/workflows/nomess.yml`；
- 下一步：把"一件事一个入口"的规则登记进 `check.rules`，把目录的严格度登记进 `scopes`，例如：

```json
"check": {"rules": [
  {"id": "R1", "level": "red", "what": "rounding money only in money.py", "why": "one rounding rule", "glob": "**/*.py", "forbid": "\\bround\\("},
  {"id": "R2", "level": "red", "what": "file I/O only in storage/", "why": "one place for paths and encodings", "glob": "src/**/*.py", "forbid": "\\bopen\\("},
  {"id": "R3", "level": "red", "what": "HTTP only through http_client", "why": "one place for retries and timeouts", "glob": "src/**/*.py", "forbid": "\\brequests\\."}]},
"allow": [{"rule": "R1", "file": "src/money.py", "reason": "the one entry point"},
          {"rule": "R2", "file": "src/storage/**", "reason": "the one entry point"},
          {"rule": "R3", "file": "src/http_client.py", "reason": "the one entry point"}],
"scopes": [
  {"paths": ["src/core/**"], "smells": {"file_lines": 400, "func_lines": 50}, "review": "strict", "why": "core: mistakes are costly"},
  {"paths": ["tools/**"], "checks": {"remove": ["D1", "S1"]}, "review": "light", "why": "one-off scripts"}]
```

CI 片段：

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

## 4. 重跑：改大小

- **变大**：在 `nomess.json` 里只改 `size`；已有的文件一律不动，新大小多出的文件第一次用到时再建。然后做第 3 节。报告现在生效的检查（`nomess.py check --rules` 里没标"not enabled"的行）。如果 `nomess.json` 里写了明确的 `check.builtin`，保持原样；告诉用户它缺新大小的哪些缺省项（medium 多 A1；large 多 C4、PL-DUP、PL-STALE）。
- **变小**：什么都不改。变小会关掉一些检查，提交闸门会把这当放宽拦下；告诉用户要由人来做：改 `size`，用 `--no-verify` 提交，并给 PR 打上 `nomess-loosen` 标签。降到 `small` 之前，先把指向系统图分页（`files.md`、`deps.md` 等）的链接都改成指向首页 `index.md`，和 `size` 一起提交；`small` 会删掉分页，留着旧链接会被 DOC1 报断链。
- **不变**：做第 3 节。
