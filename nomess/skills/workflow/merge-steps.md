# Merge steps

`nomess.py` is the command form defined at the top of the workflow skill. Merge one branch at a time on the main branch.

1. Before starting, the working tree and the index are clean (`git status --short` prints nothing); if not, stop and report what is there.
2. `git merge --no-ff --no-commit <branch>`.
3. If `git rev-parse -q --verify MERGE_HEAD` prints nothing, the branch was already merged: stop. On conflicts, resolve them and `git add` the resolved files one by one.
4. Finish with a separate `git commit`. Its `pre-commit` hook checks the merge result and refreshes the generated files (system map, path rules, lessons index, the nomess section of `AGENTS.md`) into this merge commit. Blocked by red: fix it and commit again. Why two steps: changes made to the index inside `pre-merge-commit` don't enter the merge commit (git has already computed the tree), so only the finishing `git commit` can carry the refreshed files. A plain `git merge` is still checked by `pre-merge-commit`, just not refreshed.
5. Lessons need no copying: the coding agent recorded them in the branch before its last commit, and `inbox.md` merges with `merge=union`. If check reports red L5 (an entry with a field twice, or two entries with the same title), merge those entries by hand. `/nomess:dream` verifies unverified entries later.
6. Bookkeeping: large projects set the package to `Merged` in `docs/schedule.md`, medium projects in the plan's `## Packages`; apply the doc sentences from the handback; archive the plan once it is fully done (workflow section 3). Commit this bookkeeping separately.
7. When a batch is merged: review the combined diff per its review level; run the full tests once and build and run once to the point where real data loads (the project's own commands, from `AGENTS.md` or its README); then `nomess.py check --tighten` and commit it alone (it only lowers the baseline to what is left, so fixed debt can't be spent again).
