---
name: lesson
description: >-
  记一条教训进 docs/lessons/inbox.md。参数：一句话。
disable-model-invocation: true
argument-hint: "<教训一句话>"
---

# lesson：记一条教训

教训放仓库里，写代码的子代理动手前也查得到。不用提前建任何东西：第一次 `lessons add` 会自己建 `docs/lessons/` 和 `inbox.md`。

## 不记的

- 从代码或 git 看得出来的。
- 会过期的状态（进度、某个数现在是多少）：写进排期或文档。
- 用户偏好：记个人记忆。
- 能机械判断的（"X 只许出现在 Y 里"）：写成 `nomess.json` 的规则提案交给用户，登记后跑 check 确认能报出来。

## 写成三栏

从 `$ARGUMENTS` 和本次对话提炼：
- **标题**：一句。
- **概述**：何时适用的触发场景（"改存档字段前"）+ 相关文件路径和两三个关键词，给 `lessons find` 匹配用。不写内容摘要。
- **内容**：怎么做、为什么、来源（提交号或日期）；失败的写"下次怎么避开"。

## 写入

`${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py" lessons add "<标题>" -s "<概述>" -b "<内容>"`，没对照代码核实过就加 `--unverified`；脚本把它带日期追加进 inbox，同标题的条目则原地覆盖；不手改 inbox。写完用同一脚本 `lessons find <一个关键词>` 确认能查到，回用户一行：标题 + `lessons status` 的条数。
