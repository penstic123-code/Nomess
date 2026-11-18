---
name: lean-change
description: >-
  Load before coding, fixing bugs, refactoring, adding features, choosing dependencies or designing: smallest complete change by three questions, look it up when unsure, fix root causes, no patches or defensive code.
---

# lean-change: smallest complete change

Lazy in the solution, never lazy in the reading: understand first, look for what exists first, then write the least code. Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root.

## 1. Understand first

- List every place the change must reach: callers, tests, config, data, self-descriptions in docs. The shortest diff only counts if it reaches all of them.
- Trace from entry to exit and confirm the problem really is in the link you think it is. For a bug, grep all callers first and fix once in the shared layer.
- Check the lessons library: `nomess.py lessons find <path of the file to change, or a keyword>` returns at most 3 entries; read the full text only if useful.
- Read a file before changing it, not just Grep snippets: this directory's rules (`.claude/rules/`) load only on Read, and must be re-Read after context compaction.

## 2. Three questions (stop at the first one that fully solves it)

1. Does it need to be done? Is the requirement really asking for this change, and how far should it go? Don't build what nobody asked for; name unrequested options, switches and extension points in the handback.
2. Does something already exist? Code in the repo, the standard library or platform, an installed dependency, an established open-source approach. Reuse it the way the surrounding code does; don't add a dependency for a few lines.
3. Write the least complete code. If unsure, look it up first (official docs, open-source implementations, papers) and note the source.

Of two options the same size, pick the one that gets edge cases right.

## 3. When you must look it up

Look it up first if any holds: algorithms, numerics, concurrency, protocols, file formats, security, or any problem others have surely solved; you are about to invent a mechanism, format, cache or scheduler; one attempt at the same problem already failed; you are unsure how to use a third-party library.

No need: the repo has similar code; purely mechanical changes (rename, move, table-driven replacement); the brief already gives the approach and source.

How: official docs and specs → source of mature open-source implementations → papers. One round, then stop. External queries carry no user name, email or project name.

## 4. Writing rules

- Fix the root cause, don't patch: no clamps, switches or special cases that hide symptoms. "Simple" means the system is simplest after the change, not the smallest diff; wrapping a layer to change fewer lines is a patch.
- No defensive code: don't check impossible states, don't keep fallback paths, compatibility reads, aliases or old names. Convert old data with a one-off script; code accepts only the new format and errors on invalid input.
- Never cut: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, calibration the hardware needs, anything the user explicitly asked for. Test: does this check stop bad input that really arrives (keep), or a state your own code cannot produce (delete)?
- One entry point per job, no duplicates. Use another module through its public entry point, not its internal data or private functions. Comments only explain a "why" the code cannot.
- A shortcut with a known limit gets a one-line comment: `shortcut: <limit>, <when to upgrade>`.

## 5. Tests

- Write tests only for edge behavior that is hard to deduce correctly from the code and easy to regress. What reading the code can confirm goes into the handback as "confirmed by reading code: file:line", with no test.
- One test checks one thing. No timing assertions. Don't test implementation details or cover the same behavior twice.
- During development run only the tests you changed; run the full suite once before handing back. Whether the logic is right is mostly judged by review.
- If the project has its own testing rules (in `AGENTS.md`, `CLAUDE.md` or its docs), follow them instead of this section.

## 6. Debugging

What can be deduced from code and existing data, deduce; don't schedule measurements. Propose the single most likely cause, verify it the cheapest way, then move to the next if it fails. Fix every problem found by default; only "extremely rare + fix touches many places" gets "suggest recording as a known issue". Three rounds on one problem without a conclusion: stop and hand back known facts, what was ruled out, and the next direction.

## 7. Commit and hand back

The commit runs `nomess check` in a git hook. Blocked by red: fix it, or add a top-level `allow` with a reason to `nomess.json` and name it in the handback; never `--no-verify`.

Before the last commit, record what code and git don't show: `nomess.py lessons add "<title>" -s "<when it applies: files, keywords>" -b "<what to do, why, source>" --unverified`, so the entry goes into that commit. Same title overwrites the old entry.

The handback carries these lines (add `Looked up: <link>` only when what you found changed the decision):

```
Tests: <added ones → which acceptance item each covers>; confirmed by reading code: <file:line, …>
```

---
Sources: the questions (distilled from ponytail's decision ladder), listing every place the change must reach, the never-cut list and the `shortcut:` comment are borrowed from ponytail (github.com/DietrichGebert/ponytail, MIT, skills/ponytail/SKILL.md). When you must look it up, the defensive-code test, deduction before measurement, the test rules and the handback lines are added by this plugin.
