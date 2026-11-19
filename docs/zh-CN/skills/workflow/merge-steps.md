# 合并步骤

`nomess.py` 是 workflow skill 开头定义的命令写法。在主分支上一次合入一个分支。

1. 开始前，`git status --short` 无输出；有输出就停，报告里面有什么。
2. `git merge --no-ff --no-commit <branch>`。
3. 如果 `git rev-parse -q --verify MERGE_HEAD` 没有输出，说明这个分支已经合过了：停。有冲突就解决，并把解决好的文件逐个 `git add`。
4. 用单独的 `git commit` 收尾：只有它的 `pre-commit` 钩子能把刷新后的生成文件（系统图、路径规则、教训索引、`AGENTS.md` 的 nomess 段）带进合并提交；直接 `git merge` 会检查但不刷新。被红项拦下：改掉再提交。
5. 教训不用抄：已经在分支里，`inbox.md` 靠 `merge=union` 合并。如果 check 报红 L5，手工把这些条目合并。
6. 记账：large 项目在总排期（缺省 `<docs_root>/schedule.md`，见 workflow skill 开头）里把包设为`已合`，medium 项目在方案的 `## 分包` 里设；把交回里的文档句子改进去；方案全做完就归档（workflow 第 3 节）。这次记账单独提交。
7. 合完一批：按审查级别审合起来的 diff；完整测试跑一次（有 CI 就以 CI 为准），再构建并运行一次，走到真实数据加载为止（项目自己的命令，见 `AGENTS.md` 或它的 README）；然后 `nomess.py check --tighten` 并单独提交（它把基线降到剩下的，所以修掉的欠账不能再被花掉）。
