---
name: workflow
description: >-
  Load when dispatching work, writing plans or briefs, reviewing or merging: five change tiers by what breaks if wrong, extra steps by who executes, settle ownership before big plans, trial-read before dispatch, one schedule, review by tier, mechanical rules to scripts. Not for solo coding from a brief.
---

# workflow: which process a change goes through

Project rules win: if the project's `AGENTS.md` or `CLAUDE.md` says otherwise about any step here (tier steps, trial reads, tests, review), follow the project.

Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root (`brief-template.md` and `merge-steps.md` use it too). `size` (`small` / `medium` / `large`) and `docs_root` (default `docs`, written `<docs_root>`) come from `nomess.json`. The doc places below (`<docs_root>/plans/`, `<docs_root>/schedule.md`, `<docs_root>/ownership-map.md`, `<docs_root>/systems/`) are the defaults of the plans, schedule, ownership and systems doc types; a project with its own type list (`builtin_doc_types: false`) gives each as the `doc_types` entry with that `role` (also in the "Docs go" line of `AGENTS.md`), and a step for a role it has no entry for is skipped.

## 1. Five tiers

Ask: if this change is wrong, what breaks?

| Tier | What change | Process |
|---|---|---|
| Direct | Comments, docs, formatting, local renames; behavior unchanged | Change it, no review |
| Light | Inside one module, callers unaffected: a bug fix, an internal refactor, a new private helper | Change → check; no separate review (except at `strict`) |
| Planned | Changes what one system offers but stays inside it: a new feature, a signature whose callers are all in the same system, a new config option | A few lines of plan first (what changes, which files, how to verify) → change → review the code once (any level but `off`) |
| Full | Reaches other systems or lasting data: an interface another system calls; shared data or its owner; a file, save, database or wire format; execution order between systems; deleting or migrating stored data | Adds to Planned: a written plan, owners settled, the plan reviewed before coding (section 2) |
| System | Building or rebuilding a whole system; a refactor across several systems | Adds to Full: a design doc, a prototype of the riskiest assumption, the user's sign-off, milestones (section 2) |

When unsure, go one tier up. Reading or writing data or timing owned by another system counts as Full.

**Who executes** adds steps on top of the tier:

| Executor | Adds |
|---|---|
| Yourself | Nothing: no brief, no trial read, no dispatch |
| Another agent | A brief and a trial read before dispatch (section 4); a handback (section 5) |
| Several agents in parallel | Also: one agent per package, one git worktree per agent; files, timing, owners and events don't overlap; the coordinator merges one at a time; a `small` project first runs `nomess.py init --auto --size medium` |

When the plan turns out wrong during execution, go back to the plan (section 6); don't patch around it.

## 2. Full

1. Look at the current state before writing the plan: who writes, who reads, at which point, who saves shared data; the hotspot list on `<docs_root>/system-map/index.md`. Settle the single owner of each piece of data.
2. Write the plan (section 3). `<docs_root>/plans/`, `<docs_root>/schedule.md`, `<docs_root>/ownership-map.md` and subsystem pages `<docs_root>/systems/<name>.md` are created on first need from `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/docs/` (`system-page.md` for subsystem pages). The ownership map also needs the docgen entry `"owners": {"file": "<docs_root>/ownership-map.md", "builtin": "owners"}`.
3. Review the plan: small, the user takes a look; medium and large, a fresh subagent given only the plan and the owner records checks it for conflicts. At most two rounds: the second only checks that the first round's points were fixed.
4. If another agent executes: brief, trial-read, dispatch (section 4); it hands back (section 5).
5. Review the code (section 7), then merge per `merge-steps.md`.

Irreversible operations (deleting or migrating stored data, breaking a published interface): back up or dry-run first, and run them only after the user agrees.

| `size` | Extra |
|---|---|
| `small` | None: the plan is a few lines in the conversation; owners go into `## How to use` of the system pages |
| `medium` | The plan is a file in `<docs_root>/plans/` with its packages under `## Packages`; before running packages in parallel, check by hand that their files don't overlap (no script checks this) |
| `large` | Also: `<docs_root>/schedule.md` is the only construction entry point (packages, order, files, status live only there; C4 blocks overlapping files on commit); owners go into `<docs_root>/ownership-map.md` before dispatching |

**System tier**:

1. Look up how mature projects solve it, then write a design doc in `<docs_root>/plans/`: goals, non-goals, subsystem boundaries, interfaces, data owners, options not chosen and why.
2. Prototype the riskiest assumption first; write what it proved into the design.
3. Design review: a fresh subagent (at most two rounds), then the user signs off. No production code before sign-off.
4. Split into milestones with acceptance criteria; work inside a milestone runs as Full or Planned changes.
5. After each milestone, review its combined diff against the design; when reality disagrees, fix the design first (section 6).

## 3. Plans

Copy `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/plan.md`.

- Make every decision: a cheap model can start from the plan and brief without asking. An executor making their own calls is where patches begin.
- One main plan, never "could do A or B"; one line of reasoning per trade-off; a "Not chosen, and why" section.
- **Header**: `Status:` (proposed / accepted / rejected / superseded), `Date:`, optional `Systems:`, `Supersedes:`, `Superseded-by:` (then Status is superseded). Field names follow `lang`.
- **Archive**: done, rejected or superseded plans move to `<docs_root>/plans/archive/YYYY-MM-DD-<name>.md`, never deleted; done → accepted. No sequential numbers: parallel agents would grab the same one.

## 4. Briefs and trial reading

Fill all seven sections of `brief-template.md`. Copy only this package's part of the plan; check every file:line yourself and note the commit; split acceptance criteria into **tests** (edge behavior hard to deduce and easy to regress) and **confirmed by reading code**.

**Trial-read before dispatch**: give the plan path (small: the plan text) and the brief to the `nomess:trial-reader` subagent. Answer its questions in the plan or brief and trial-read once more; questions still open after the second round go to the user.

Coding agents don't edit shared docs: doc sentences go in the handback.

## 5. Handback

Check the three items of `brief-template.md` section 7; send back a handback missing any.

## 6. Plan rework

Triggers: the brief disagrees with reality; review finds a design hole; tests or evals contradict a plan premise.

- Executor: stop and hand back the failed premise and what you saw; never edit the plan or work around it.
- Coordinator: halt the affected packages and mark them `Rework` (large: in the schedule; medium: in the plan's Packages); fix the premise where it is written (plan, schedule or ownership map), never in a copy; append `Change log: <date>, <what>, <why>` to the plan; back to `Todo` once the brief is fixed. Commits of halted packages are not merged.
- Small projects: fix the plan and redo. Small rework (no other package affected): fix plan and brief, trial-read the changed parts, redispatch. Large (owners, interfaces, other packages, or unsure): review the plan again; merged packages that relied on the premise get a redo package. A second rework of the same package: ask the user.

## 7. Review

Read and follow `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md`: it says what is reviewed at which level and how comments are verified.

- Code is reviewed once. Fixes for accepted comments are not reviewed again, unless they change the design or add files: then review only that fix, once.
- Whether logic is right is mostly judged by review, not tests: don't ask executors for tests beyond the brief's edge cases.

## 8. Commit gate and rules

The git hooks run `nomess check` on each commit and block red; bypassing them is blocked. Red: fix it, or add a top-level `allow` with a `reason` (always reviewed).

After a new pitfall, first ask whether it can become a rule instead of a text reminder: `check.rules` in `nomess.json` (`forbid` / `require` / `cmd`), `arch` for constraints between subsystems, a docgen generated section for two things that must agree. What needs judgment the automatic tidy (`nomess:dream`) turns into a path rule.

## 9. Docs

- Docs go only into document-type locations (listed in the nomess section of `AGENTS.md`; new `.md` elsewhere is blocked). Nothing fits: record a lesson titled `Doc gap: …`.
- Developer docs (`CONTRIBUTING` and the like) are edited in place only; public docs (`README`, `CHANGELOG`, a docs site) are never changed automatically.
- Write as things are now: change old wording in place, never append "update: …".

## 10. Agents

One agent, one job, then it ends; switch agents between milestones with a one-page handover. Don't work around permission blocks or ask others to do it.

---
Sources: Google Antigravity teamwork docs (acceptance criteria, file handoff), MADR (decision records), lint-staged / pre-commit (commit-time checks), lessons from the author's projects.
