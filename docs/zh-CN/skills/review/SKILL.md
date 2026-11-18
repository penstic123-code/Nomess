---
name: review
description: >-
  按 review.level 审一次改动并逐条核实意见。参数：可选的基点提交或分支。
disable-model-invocation: true
argument-hint: "[基点提交或分支]"
---

# review：审一次改动

审查者也会错：每条意见都先重读它指的代码再决定采不采纳（第 4 节）。审查者只看 diff 和设计片段，不看作者的交回、不看你的结论。

下文的 `nomess.py` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`，在项目根执行。审查者的全部输入就是 `nomess.py review-input <base> [excerpt file]`：它拿 HEAD 和基点比，所以要先把改动提交。

## 1. 准备

1. 基点：有参数用 `$ARGUMENTS`；没有就用 `git merge-base <main_branch> HEAD`（`main_branch` 在 `nomess.json` 里）。按批审用整批的合并基点。
2. 设计片段：只摘和这次改动有关的（方案里相关的段落、改动碰到的归属条目），写进 `.nomess/review-excerpt.md`；轻流程没有方案就写"无"。
3. 跑 `nomess.py review-input <base> .nomess/review-excerpt.md`，只留它的第一行（`| head -n 1`；PowerShell 用 `| Select-Object -First 1`）：审查级别。末尾有 `[must-review]` 表示脚本发现了必审项（新的 `allow` 或 `doc_types` 条目、新冻结、放宽、L6）。

## 2. 审不审

`off` 下什么都不审（放宽仍要 PR 标签 `nomess-loosen`）。其他级别下这些一定审：第一行带 `[must-review]` 的；简报以外的改动（哪怕一行）；中流程和全套改动（每个包审一次）；系统档（每个里程碑合起来审一次）。其余按下表：

| 级别 | 按包 | 按批（合起来的 diff） |
|---|---|---|
| `light` | 不审 | 审，文档、配置、测试不看 |
| `standard` | 逻辑代码审；轻流程改动、只改文档 / 配置 / 模板的不审 | 审 |
| `strict` | 都审，轻流程改动也审 | 审 |

不该审就告诉用户"按 `<级别>` 不审"和理由，结束。

## 3. 选审查者（够用的里面最便宜的）

- `nomess.json` 配了 `review.cmd`：跑 `nomess.py review-input --cmd <base> .nomess/review-excerpt.md`，它把清单和输入交给 `review.cmd` 并打印输出。它报失败时告诉用户"审查失败"，不能当成"没发现问题"。
- 没配：派 `nomess:reviewer` 子代理。
  - 普通代码：sonnet。逻辑多、有取舍、跨系统：`model: opus`；`strict` 下有取舍的一律用最强的模型。不用 haiku：它漏的逻辑太多，省不了什么。
  - 提示词只给：基点、设计片段路径、一句"这次改动要做什么"。
  - 按批审：加一句"只查包与包之间的语义冲突"。

## 4. 核实

收到的每条意见，重读它指的代码，写"采纳"或"不采纳 + 理由"。标了"建议做成 check 规则"的单独列给用户。

## 报告（给用户）

一张表：意见（文件:行 + 一句）| 采纳 / 不采纳 | 理由。最后一行：要改的几条由谁改。本 skill 不改代码。
