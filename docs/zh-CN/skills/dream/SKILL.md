---
name: dream
description: >-
  整理记忆和教训库：先体检出提案，用户确认后一次做完、提交、给出 diff。参数：空 = 出提案；"execute [strike N…]" = 执行。
disable-model-invocation: true
argument-hint: "[execute [strike N…]]"
context: fork
model: sonnet
---

# dream：整理记忆和教训

`nomess.py` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`，在项目根执行。分两次调用：先出提案，用户看过再"execute"。提案存 `.nomess/dream-proposal.md`（不提交）。下文字段名是英文的；`zh-CN` 项目写中文的。

## A. 出提案（`$ARGUMENTS` 为空）

只读：提案文件是你唯一写的文件；只跑下面的命令、Read、Grep 和 `git log`。只读体检点名的文件和 `inbox.md`；核对事实用 Grep 和 `git log -S <词> --oneline`。

1. 定位：`nomess.py status --json --no-exec`。项目记忆 = `memory_dir`。为空就不猜：只整理教训库，把 `memory_problem` 写在提案第一行里记忆路径的位置。
2. 体检，只看报告：`nomess.py check --memory <项目记忆> --all --no-exec` 和 `nomess.py check --all --no-exec`。
3. 对每个点名的条目和每条 inbox：文件还在吗？做法还成立吗？仓库 docs 里已有的事实，记忆里最多留一行链接。
4. 写提案。第一行：记忆目录和教训库的绝对路径，以及记忆是怎么定位的（`memory_source`）。然后每条一行：编号 + 动作 + 理由，动作只有这几种：

   ```
   1. 合并 a.md + b.md → a.md：讲同一件事（M7）
   2. 删除 c.md：X 已在 <提交号> 去掉
   3. 改写 d.md 第二段：数字已变成 Y（见 <文件>）
   4. 挪层 e.md → docs/<文件>：是项目事实
   5. inbox「标题」→ 归入 g.md / 新建主题页 / 删
   6. 做成路径规则 <文件>#<标题>：路径 src/x/**；规则 <不超过 25 词 / 40 个汉字>
   7. 做成 check 规则：<id，forbid/require/cmd，一句话> 写进 check.rules
   8. 登记进 arch：<layers / independent / forbid / relations 项，一句话>
   9. 把 smells.<key> 从 A 降到 B：<为什么>
   ```

   - 先问教训能不能变成 check 规则（7）或 `arch` 项（8）；只有要 AI 判断的才做成路径规则（6），而且只给会反复用的 `状态: 已核实` 条目。条目原来管的路径照抄，不放大。
   - 阈值只许降（9）：调高是放宽，提交闸门会拦；改写成给人看的备注。
   - 两条冲突时，留对的，改写或删掉另一条；旧说法在 git 历史里。
   - 末尾一行：记忆索引现在多少 token、执行后多少（不许变多；中文按字数，其余字符数 / 4）。
5. 回用户：提案全文 + "回 `/nomess:dream execute`，或 `/nomess:dream execute strike 2 5`"。到此为止。

## B. 执行（`$ARGUMENTS` 以 "execute" 开头）

1. 读提案文件（没有就停）；划掉的编号不做。
2. 先提交，这样下面的一切都能用 `git revert` 撤回：
   - 记忆目录：`git -C <目录> rev-parse --show-toplevel`。不是仓库 → `git init`，并设 `core.autocrlf false`。自己就是仓库 → 有未提交的改动就 `git -C <目录> add -A -- .` 并提交"pre-dream snapshot"。在别人的仓库里 → 不在那里提交，回报里说明。
   - 项目仓库：`git diff --cached --name-only` 有输出（用户自己暂存了东西），第 5 步就不提交项目仓库，并说明。
3. 一次做完剩下的所有条目：
   - 改指向被删、被合并、被挪走的页的 `[[…]]` 链接和索引行；索引一个主题一行 `[主题](文件) — 何时用`。
   - 教训：用 `nomess.py lessons add` 写（同标题原地覆盖）；处理完的 inbox 条目删掉。第一次建主题页时，再把 `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/docs/lessons/README.md` 拷进教训库目录，并加 docgen 项 `"lessons-index": {"file": "<教训库目录>/README.md", "builtin": "lessons-index"}`。
   - 路径规则：给条目加 `路径:` 和 `规则:`（系统页则加在 `## 坑` 下）。
   - check 规则、`arch` 项、阈值：改 `nomess.json`（写法见 `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`）；如果 `nomess.py check` 对新规则或 `arch` 项报红，就撤掉它并报告（绝不冻结）。规则登记后删掉那条教训。
4. 校验，没过就改到过：`nomess.py refresh`；`nomess.py check` 无红；`nomess.py check --memory <记忆目录>` 无红（没有断链）；记忆索引 token 不比之前多。
5. 每个仓库提交一次，不推送：记忆仓库 `git -C <目录> add -A -- .` 后提交"dream: <几项>"；项目仓库：把改的教训、docs、`nomess.json` 和 `.claude/rules/nomess/` 逐个 `git add`，再提交。
6. 删提案文件。回用户：每个仓库的 `git diff --stat <之前>..<之后>`、提交号、没做的条目和原因，以及撤回命令 `git -C <目录> revert <提交号>`。
