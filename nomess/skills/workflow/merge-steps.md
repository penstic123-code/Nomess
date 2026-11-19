# Merge steps

`nomess.py` is the command form defined at the top of the workflow skill. Merge one branch at a time on the main branch.

1. Before starting, `git status --short` prints nothing; if not, stop and report what is there.
2. `git merge --no-ff --no-commit <branch>`.
3. If `git rev-parse -q --verify MERGE_HEAD` prints nothing, the branch was already merged: stop. On conflicts, resolve them and `git add` the resolved files one by one.
4. Finish with a separate `git commit`: only its `pre-commit` hook can put the refreshed generated files (system map, path rules, lessons index, the nomess section of `AGENTS.md`) into the merge commit; a plain `git merge` is checked but not refreshed. Blocked by red: fix it and commit again.
5. Lessons need no copying: they are already in the branch, and `inbox.md` merges with `merge=union`. If check reports red L5, merge those entries by hand.
6. Bookkeeping: large projects set the package to `Merged` in the schedule (`<docs_root>/schedule.md` by default; see the top of the workflow skill), medium projects in the plan's `## Packages`; apply the doc sentences from the handback; archive the plan once it is fully done (workflow section 3). Commit this bookkeeping separately.
7. When a batch is merged: review the combined diff per its review level; run the full tests once (if there is CI, its result counts) and build and run once to the point where real data loads (the project's own commands, from `AGENTS.md` or its README); then `nomess.py check --tighten` and commit it alone (it lowers the baseline to what is left, so fixed debt can't be spent again).
