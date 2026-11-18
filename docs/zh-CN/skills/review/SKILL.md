---
name: review
description: >-
  按 review.level 审一次改动并逐条核实意见。参数：可选的基点提交或分支。
disable-model-invocation: true
argument-hint: "[基点提交或分支]"
---

# review：审一次改动

下文的 `nomess.py` 指 `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`。都在项目根（`nomess.json` 所在目录）执行。审查者的全部输入就是 `nomess.py review-input <base> [excerpt file]`：它拿 HEAD 提交和基点比，所以要先把改动提交。它不跑项目代码。

## 1. 准备

1. 基点：有参数用 `$ARGUMENTS`；没有就用 `git merge-base <main_branch> HEAD`，`main_branch` 在 `nomess.json` 里。按批审用整批的合并基点。
2. 设计片段：只摘和这次改动有关的——方案里相关的段落、改动碰到的归属条目。写进 `.nomess/review-excerpt.md`（`.nomess/` 不提交）；轻流程没有方案就写"无"。不给整份方案、不给作者的交回、不给你的结论。
3. 跑 `nomess.py review-input <base> .nomess/review-excerpt.md`，只留它的第一行（`| head -n 1`；PowerShell 用 `| Select-Object -First 1`）：审查级别（`review.level`）。如果这行末尾有 `[must-review]`，说明审查输入里有必审部分（新的 `allow`、新冻结、B1/B2 或放宽）。

## 2. 审不审

| 级别 | 按包（一个包的 diff） | 按批（一批合起来的 diff） |
|---|---|---|
| `off` | 不审 | 不审 |
| `light` | 不审（轻档改动：只在一个模块内、调用方不受影响，不单独审） | 审，文档、配置、测试不看 |
| `standard` | 逻辑代码审；只改文档、配置、模板的不审；轻档改动（只在一个模块内、调用方不受影响）不审 | 审 |
| `strict` | 都审，轻档改动也审 | 审 |

`off` 下什么都不审，下面这些也不审（放宽仍要 PR 标签 `nomess-loosen`）。其他级别都要审：第一行带 `[must-review]` 的（先看这个，再查表）；简报以外的改动（哪怕一行）；中档改动（改了一个系统对外的功能但没出这个系统；light / standard / strict 下都单独审一次代码）；全套流程的改动（改文件或存档格式、改接口、改执行时机或数据主人）；新加了 `allow` 的提交（列在审查输入的必审部分）；系统档：每个里程碑合起来审一次。

不该审就告诉用户"按 `<级别>` 不审"和理由，结束。

## 3. 选审查者（够用的里面最便宜的）

- `nomess.json` 配了 `review.cmd`：凡是要审的都交给它，不派子代理。在项目根跑 `nomess.py review-input --cmd <base> .nomess/review-excerpt.md`：它把审查清单和审查输入只走标准输入交给 `review.cmd`（不拼进 shell 命令），并打印它的输出。
  非零退出、超时都报"审查失败"（附 stderr），不能当成"没发现问题"。
- 没配：派 `nomess:reviewer` 子代理。
  - 普通代码：缺省 sonnet。逻辑多、有取舍、跨系统：指定 `model: opus`；`strict` 下有取舍的一律用最强的模型。不用 haiku：它漏的逻辑太多，省不了什么。
  - 提示词只给：基点、设计片段路径 `.nomess/review-excerpt.md`、一句"这次改动要做什么"。审查者自己跑 `review-input`、自己读清单。
  - 按批审：加一句"只查包与包之间的语义冲突"。

## 4. 核实

收到的每条意见，重读它指的代码，写"采纳"或"不采纳 + 理由"。审查者也会错。标了"建议做成 check 规则"的单独列给用户。

## 报告（给用户）

一张表：意见（文件:行 + 一句）| 采纳 / 不采纳 | 理由。最后一行：要改的几条由谁改。本 skill 不改代码。
