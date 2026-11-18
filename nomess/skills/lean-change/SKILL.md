---
name: lean-change
description: >-
  Load before coding, fixing bugs, refactoring, adding features, choosing dependencies or designing: smallest complete change via a decision ladder, look it up when unsure, fix root causes, no patches or defensive code.
---

# lean-change: smallest complete change

Lazy in the solution, never lazy in the reading: understand first, look for what exists first, then write the least code. Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root.

## 1. Understand first

- List every place the change must reach: callers, tests, config, data, self-descriptions in docs. The shortest diff only counts if it reaches all of them.
- Trace from entry to exit and confirm the problem really is in the link you think it is. For a bug, grep all callers first and fix once in the shared layer.
- Check the lessons library: `nomess.py lessons find <path of the file to change, or a keyword>` returns at most 3 entries; read the full text only if useful.
- Read a file before changing it, not just Grep snippets: this directory's rules (`.claude/rules/`) load only on Read, and must be re-Read after context compaction.

## 2. Decision ladder (stop at the first rung that fully solves it)

| Rung | Question | If yes |
|---|---|---|
| L1 | Does it need to exist? | Don't build it; name unrequested options, switches and extension points in the handback |
| L2 | Is it already in the repo (function, tool, convention)? | Reuse it the way the surrounding code does |
| L3 | Does the standard library / platform have it? | Use it (use the project's wrapper if there is one) |
| L4 | Can an installed dependency do it? | Use it; don't add a dependency for a few lines |
| L5 | Unsure, or the industry has most likely solved it? | Look it up first; follow established practice and cite the source |
| L6 | Can one line say it? | One line |
| L7 | None of the above | Write the least code that works |

Of two options the same size, pick the one that gets edge cases right.

## 3. When you must look it up (L5)

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

The handback carries these lines:

```
Ladder: L<n> (why it stopped here); Looked up: <link, or "not looked up: reason">
Tests: <added ones → which acceptance item each covers>; confirmed by reading code: <file:line, …>
Lesson: <title recorded before the last commit; "none" if none>
```

Example: `Ladder: L5 → L4 (dedupe with the installed xxhash); Looked up: xxhash README`

---
Sources: the decision ladder (L1–L4, L6–L7), listing every place the change must reach, the never-cut list and the `shortcut:` comment are borrowed from ponytail (github.com/DietrichGebert/ponytail, MIT, skills/ponytail/SKILL.md). L5, when you must look it up, the defensive-code test, deduction before measurement, the test rules and the handback lines are added by this plugin.
