---
name: workflow
description: >-
  Load when dispatching work, writing plans or briefs, reviewing or merging: three change tiers, settle ownership before big plans, trial-read before dispatch, one schedule, review by tier, mechanical rules to scripts. Not for solo coding from a brief.
---

# workflow: which process a change goes through

Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root; the support files `brief-template.md` and `merge-steps.md` use this short form too. Project size is `size` in `nomess.json` (`small` / `medium` / `large`); it only decides which extra steps the Full tier carries (section 2) and the defaults of checks and review level.

Project rules win: if the project's `AGENTS.md` or `CLAUDE.md` says otherwise about any step here (how many steps a tier has, whether to trial-read, how to test, when to review), follow the project. Review can also be turned off entirely with `review.level: "off"`, globally or per directory in `scopes`.

## 1. Three tiers

| Tier | What change | Process |
|---|---|---|
| Full | Cross-system; changes a file or save format; changes an interface; changes execution timing or a data owner | Plan → review the plan → trial-read → dispatch → code → handback → review the code → merge |
| Light | A single-point fix | Dispatch directly, review the code once |
| Direct | Comments, docs | Change it yourself, no review |

When unsure, go one tier up. Reading or writing data or timing owned by another system counts as Full.

## 2. Full

1. Look at the current state before writing the plan: who writes, who reads, at which point, who saves shared data; the hotspot list on `docs/system-map/index.md`. Settle the single owner of each piece of data.
2. Write the plan (section 3). 3. Review the plan: a fresh subagent given only the plan and the owner records checks it for conflicts. 4. Write briefs and trial-read them (section 4). 5. Dispatch. 6. Code and hand back (section 5). 7. Review the code (section 7). 8. Merge per `merge-steps.md`.

Extra steps by size:

| `size` | Extra |
|---|---|
| `small` | None: the plan is a few lines in the conversation; reviewing it can be the user taking a look; owners go into `## Details` of the `docs/systems/` pages |
| `medium` | Owners as in small. The plan is a file in `docs/plans/`; its packages are listed in the plan under `## Packages`; before running packages in parallel, check by hand against that list that their files don't overlap (no script checks this) |
| `large` | Also: `docs/schedule.md` is the only construction entry point (packages, order, files, status live only there; C4 checks overlapping files on commit); settle owners in `docs/ownership-map.md` before dispatching |

When the plan turns out wrong during execution, go back to the plan layer (section 6); don't patch around it.

## 3. Plans

Copy `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/plan.md` (`lang` from `nomess.json`).

- Make every decision: a cheap model can start after reading the plan and brief without asking. An executor making their own calls is where patches begin.
- One main plan only, never "could do A or B"; one line of reasoning per trade-off; a "Not chosen, and why" section (this is the decision record).
- **Header** at the top: `Status:` (proposed / accepted / rejected / superseded), `Date:`, optional `Systems:` (names from `systems`), `Supersedes:`, `Superseded-by:` (then Status must be superseded). Field names follow `lang`.
- **Archive**: done, rejected or superseded plans move to `docs/plans/archive/YYYY-MM-DD-<name>.md`, never deleted; done → accepted. No sequential numbers: parallel agents would grab the same one.

## 4. Briefs and trial reading

Write the seven sections of `brief-template.md`; don't dispatch with one missing. Copy only this package's part of the plan; check every file:line yourself and note the commit; give verifiable acceptance criteria, split into **tests** (edge behavior hard to deduce from code and easy to regress) and **confirmed by reading code**.

**Trial-read before dispatch**: give the plan path (small: the plan text) and the brief to the `nomess:trial-reader` subagent; it lists only questions still open after reading. Answer them in the plan or brief and trial-read again; dispatch only on "none".

**Parallel**: one agent per package; run in parallel only when files, timing, owners and events don't overlap. One working tree has one committer: each parallel agent works in its own git worktree, and the coordinator merges into the main branch one at a time. Coding agents don't edit shared docs: doc sentences go in the handback.

## 5. Handback

Eight lines; missing lines get sent back: commit hash; check result in one line; failed premise ("none" if none); changes outside the brief ("none" if none); premises deduced but not measured; ladder line; tests (which were added and which acceptance item each covers; which items were confirmed by reading code, as `file:line`); lesson (title of the entry recorded with `lessons add --unverified` before the last commit and carried in it; "none" if none).

## 6. Plan rework

Triggers: the brief disagrees with reality; review finds a design hole; tests or evals contradict a plan premise.

- Executor: stop, hand back as usual with the failed premise and what you saw; never edit the plan or work around it.
- Coordinator: halt the affected packages and mark them `Rework` (large: in the schedule; medium: in the plan's Packages); fix the premise where it is written (plan, schedule or ownership map), never in a copy; append `Change log: <date>, <what>, <why>` to the plan; back to `Todo` once the brief is fixed. Commits of halted packages are not merged.
- Small projects have no packages: fix the plan and redo. Small rework (no other package affected): fix plan and brief, trial-read the changed parts, redispatch. Large (owners, interfaces, other packages, or unsure): review the plan again; merged packages that relied on the premise get a redo package.

## 7. Review

Follow `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` (Read it; `/nomess:review` is for the user). The review level of a change is the first line of `nomess.py review-input <base>` (base: the merge base with the main branch): the strictest level among the changed files.

- **Reviewed at every level**: changes outside the brief (even one line); every package of a Full change; any commit that adds an `allow`.
- Re-read the code for every comment and write "accepted" or "rejected + reason".
- Whether logic is right is mostly judged by review, not by tests. During development run only the tests you touched; the full suite runs once before handback.

## 8. Commit gate and rules

The git hooks (`pre-commit`, `pre-merge-commit`) run `nomess check` on what is being committed and, on the main branch, refresh generated files into the same commit.

- Blocked by red: fix it, or add a top-level `allow` with a `reason` (always reviewed). Never `--no-verify`, never touch `core.hooksPath`.
- Mechanically checkable rules go into `check.rules` of `nomess.json` instead of text reminders: `forbid` (a pattern only allowed in the files listed in `allow`), `require` (files must have a header), `cmd` (the project's own check). Constraints between subsystems go into `arch`. Two things that must agree become a docgen generated section.
- Red is a definite error and blocks commits; yellow is heuristic and only warns. After hitting a new pitfall, first ask whether it can become a rule; what needs judgment gets promoted by `/nomess:dream` into a path rule.

## 9. Size

`nomess.py status` prints a size suggestion when its signals cross a line (parallel branches, files changed on both sides of merges, lessons piling up, subsystem count; `status --suggest` lists them). The person decides: upgrade by rerunning `/nomess:init`; a downgrade is a loosening, so it goes through the person's loosening path (they commit with `--no-verify`, the PR gets the `nomess-loosen` label).

## 10. Agents

One agent, one job, then it ends; switch agents between milestones with a one-page handover. Three rounds on one problem without a conclusion: hand back. Don't work around permission blocks or ask others to do it. In git, add only your own files, no `commit -a`, no push.

---
Sources: Google Antigravity teamwork docs (acceptance criteria, file handoff), MADR (decision records), lint-staged / pre-commit (commit-time checks), lessons from the author's projects.
