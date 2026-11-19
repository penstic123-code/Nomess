---
name: dream
description: >-
  把教训、文档和记忆整理成一个可撤回的提交。会话钩子让调时（参数 "auto"）或用户说整理文档/记忆时调；"apply N…" 执行 .nomess/dream-notes.md 里的条目。
argument-hint: "[auto | apply N…]"
context: fork
model: sonnet
---

# dream：整理教训、文档和记忆

下面的 `nomess` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`，在项目根目录运行。只用 `nomess` 命令和 Read、Grep、Edit、Write：这些不弹权限确认。不要自己跑 `git` 或别的 shell 命令（会弹窗）；核实历史用 `nomess dream git-log <词>`。下面的字段名用英文；`zh-CN` 项目写中文字段名。

## A. 整理（参数为空或 `auto`，两者相同）

1. `nomess dream begin`。退出 3（另一次整理占着锁）：回它那一行，停。它打印工作清单、worktree、记忆目录（"没定位到"就只整理项目）、notes 写在哪。
2. 按下面的动作逐条做。只改那个 worktree（它的路径 + 仓库相对路径）和记忆目录里的文件，绝不改主检出。只读清单点名的东西；对着 worktree 里的代码用 Read、Grep 和 `nomess dream git-log <词>` 核实。
3. `nomess dream land`：它检查这次整理并落到当前分支，或者整次丢弃并说明原因。原样回它打印的那一行。被丢弃了不要修了重试。中途放弃：`nomess dream abort`。

挪动或删除文件：`nomess dream mv <旧> <新>` / `nomess dream rm <路径>`（路径相对 worktree，记忆目录里的用绝对路径；退出 2 是被拒：不动那个文件，写一条 note）。

## B. 动作（按工作清单的类）

教训（worktree 里教训目录下的文件；一条是 `## 标题` 加若干 `键: 值` 行）：
- **inbox**：每条挪进它所属的主题页，或新建主题页 `<教训目录>/<主题>.md`，或删掉；然后从 `inbox.md` 里去掉。`<教训目录>/README.md` 不存在时，把 `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/docs/lessons/README.md` 拷过去；`nomess.json` 的 docgen 里没有 `lessons-index` 时，登记它写成 note。
- **标题近似**：合成一条。两条冲突时留对的那条；旧说法留在 git 历史里。
- **未核实**：对着代码核实。对 → `Status: verified`；不对 → 改写或删掉。带 `Source: external …` 的条目你永远不改成已核实、也不删那一行（否则 land 整次丢弃）：它的核实写成 note。
- **路径和规则**：反复用到的已核实条目加 `Paths:`（照抄条目已覆盖的路径，不放大）和 `Rule:`（英文 25 词 / 中文 40 字以内）。
- **缺别名**：给经手的条目加一行 `Aliases:`，逗号分隔：中英都写，含常见说法和缩写。
- **文档缺口**（标题以 `Doc gap:` / `文档缺口:` 开头）：汇总成一条 note，提议登记新文档类型或给系统页加固定段；写进 note 后删掉这些条目。

文档（只有项目文档根、教训目录、已有的开发者文档和 `AGENTS.md` 的生成段可写；碰了别的 land 整次丢弃）：
- **方案**（PL-DUP、PL-STALE、PLN2）：同一件事写了两份 → 合成一份，删掉另一份并改好链接。过时方案 → 挪进 `<方案目录>/archive/YYYY-MM-DD-<名>.md`（方案目录缺省 `<docs_root>/plans`，或 `doc_types` 里 `role: plans` 的条目），写 `Status: superseded` 和 `Superseded-by:`。
- **排期里已合的行**：每行挪进它所属方案末尾的变更记录；排期只留没做完的行。
- **DOC4 放错位置 / 散落 .md**：看得出类型的挪进该类型的位置并改链接；重复的合并，过时的归档。哪类都不像的留在原处（文档目录把它列为未归类），写一条 note 提议新类型。
- **DOC5 孤儿页**：从它该挂的页链过去，或合并掉。
- **DOC6 超长**：原页改成概要页（这是什么、要点、往下看哪页），细节按主题拆到同一文件夹的子页（`systems/render.md` → `systems/render-shadows.md`），概要页链过去。不加目录层级。系统页的四段固定标题留在概要页；系统页的子页开头也写三行头（`这是什么：` / `为什么要有：` / `和谁配合：`），否则 DOC3 报黄。
- **过时引用**（提到的路径已不存在）：项目文档 → 对着代码改掉或删掉那句；开发者文档 → 就地改（绝不新建、删除、挪动）；对外文档 → 只写 note。
- **记忆超预算**：合并、精简、删除；项目事实搬进对应的 docs 页，记忆里留一行链接。索引保持一个主题一行 `[主题](文件) — 何时用`，改好 `[[…]]` 链接。

只写现在的样子：旧说法直接改掉，不追加"更新：…"。

## C. notes：要人定的

写进 worktree 里的 `.nomess/dream-notes.md`，一行一条、带编号（land 会追加到主检出的那份）：一切要改 `nomess.json` 的（检查规则、`arch` 条目、阈值、文档类型、生成段）；外部来源条目的核实；拿不准的删除；新文档类型；可能过时的对外文档。

## D. `apply N…`

在主检出里执行 `.nomess/dream-notes.md` 的第 N… 条（不用 worktree，不跑 `begin` / `land`）；这时可以改 `nomess.json`（格式见 `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`）。外部来源条目只有代码确认了才改成已核实，同时去掉它的 `Source:` 行。新规则或 `arch` 条目让 `nomess check` 变红的，去掉并报告，绝不冻结；规则登记好后删掉那条教训。然后 `nomess refresh`、`nomess check`，从 notes 里删掉做完的行，不提交，回一行：做了什么、哪些没做及原因。调高阈值是放宽，提交闸门会挡：说明要人来提交。
