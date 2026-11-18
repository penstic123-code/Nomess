# 合并步骤

`nomess.py` 是 workflow skill 开头定义的命令写法。在主分支上一次合入一个分支。

1. 开始前，工作树和暂存区是干净的（`git status --short` 无输出）；不干净就停，报告里面有什么。
2. `git merge --no-ff --no-commit <branch>`。
3. 如果 `git rev-parse -q --verify MERGE_HEAD` 没有输出，说明这个分支已经合过了：停。有冲突就解决，并把解决好的文件逐个 `git add`。
4. 用单独的 `git commit` 收尾。它的 `pre-commit` 钩子会检查合并结果，并把生成文件（系统图、路径规则、教训索引、`AGENTS.md` 的 nomess 段）刷新进这个合并提交。被红项拦下：改掉再提交。为什么分两步：在 `pre-merge-commit` 里对暂存区做的改动进不了合并提交（git 已经算好了树），只有收尾的 `git commit` 能带上刷新后的文件。直接 `git merge` 仍会被 `pre-merge-commit` 检查，只是不刷新。
5. 教训不用抄：写代码的代理在最后一次提交前已记在分支里，`inbox.md` 靠 `merge=union` 合并。如果 check 报红 L5（一条里同一字段出现两次，或两条同标题），手工把这些条目合并。`/nomess:dream` 之后会核实未核实的条目。
6. 记账：large 项目在 `docs/schedule.md` 里把包设为`已合`，medium 项目在方案的 `## 分包` 里设；把交回里的文档句子改进去；方案全做完就归档（workflow 第 3 节）。这次记账单独提交。
7. 合完一批：按审查级别审合起来的 diff；完整测试跑一次，再构建并运行一次，走到真实数据加载为止（项目自己的命令，见 `AGENTS.md` 或它的 README）；然后 `nomess.py check --tighten` 并单独提交（它只把基线降到剩下的，所以修掉的欠账不能再被花掉）。
