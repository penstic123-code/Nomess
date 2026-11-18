---
name: dream
description: >-
  Tidy memory and the lessons library: health check and proposal first; after user confirmation do it all at once, commit, show the diff. Argument: empty = propose; "execute [strike N…]" = execute.
disable-model-invocation: true
argument-hint: "[execute [strike N…]]"
context: fork
model: sonnet
---

# dream: tidy memory and lessons

`nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root. Two calls: propose, then "execute" after the user has looked. The proposal goes to `.nomess/dream-proposal.md` (not committed). Field names below are the English ones; in a `zh-CN` project write the Chinese ones.

## A. Propose (`$ARGUMENTS` empty)

Read-only: the proposal file is the only file you write; run only the commands below, Read, Grep and `git log`. Read only what the health check names and `inbox.md`; verify facts with Grep and `git log -S <word> --oneline`.

1. Locate: `nomess.py status --json --no-exec`. Project memory = `memory_dir`. If it is empty, don't guess: tidy only the lessons library and write `memory_problem` in place of the memory path in the proposal's first line.
2. Health check, read only the reports: `nomess.py check --memory <project memory> --all --no-exec` and `nomess.py check --all --no-exec`.
3. For each named entry and each inbox entry: does the file still exist, does the practice still hold? Facts already in the repo docs keep at most one link line in memory.
4. Write the proposal. First line: the absolute paths of the memory directory and the lessons library, and how memory was located (`memory_source`). Then one line per item, number + action + reason, using only these actions:

   ```
   1. merge a.md + b.md → a.md: same topic (M7)
   2. delete c.md: X was removed in <commit>
   3. rewrite d.md paragraph 2: the number is now Y (see <file>)
   4. move e.md → docs/<file>: it is a project fact
   5. inbox "title" → into g.md / new topic page / delete
   6. make path rule <file>#<title>: Paths src/x/**; Rule <at most 25 words / 40 CJK characters>
   7. make check rule: <id, forbid/require/cmd, one sentence> in check.rules
   8. register in arch: <layers / independent / forbid / relations entry, one sentence>
   9. lower smells.<key> from A to B: <why>
   ```

   - Ask first whether a lesson can become a check rule (7) or an `arch` entry (8); only what needs AI judgment becomes a path rule (6), and only for `Status: verified` entries that recur. Copy the paths the entry already covers; don't widen.
   - Thresholds may only go down (9): raising one is a loosening the commit gate blocks; write it as a note for the person instead.
   - When two entries conflict, keep the true one and rewrite or delete the other; old wording stays in git history.
   - Last line: tokens of the memory index now and after (must not grow; CJK by character count, the rest characters / 4).
5. Reply with the full proposal + "reply `/nomess:dream execute`, or `/nomess:dream execute strike 2 5`". Stop here.

## B. Execute (`$ARGUMENTS` starts with "execute")

1. Read the proposal file (none: stop); drop the struck numbers.
2. Commit first, so everything below can be undone with `git revert`:
   - Memory directory: `git -C <dir> rev-parse --show-toplevel`. Not a repo → `git init` it and set `core.autocrlf false`. It is its own repo → `git -C <dir> add -A -- .` and commit "pre-dream snapshot" if anything is uncommitted. It sits inside another repo → don't commit there; say so in the reply.
   - Project repo: if `git diff --cached --name-only` prints anything (the user staged something), don't commit the project repo in step 5; say so.
3. Do all remaining items in one go:
   - Update the `[[…]]` links and index lines pointing to deleted, merged or moved pages; the index has one line per topic `[topic](file) — when to use`.
   - Lessons: write with `nomess.py lessons add` (same title overwrites in place); delete processed inbox entries. The first time topic pages are created, also copy `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/docs/lessons/README.md` to the lessons directory and add the docgen entry `"lessons-index": {"file": "<lessons dir>/README.md", "builtin": "lessons-index"}`.
   - Path rule: add `Paths:` and `Rule:` to the entry (or under `## Pitfalls` on a system page).
   - Check rule, `arch` entry, threshold: edit `nomess.json` (format in `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`); if `nomess.py check` then reports red for a new rule or `arch` entry, drop it and report it (never freeze it). Delete the lesson once its rule is registered.
4. Validate and fix until it passes: `nomess.py refresh`; `nomess.py check` has no red; `nomess.py check --memory <memory dir>` has no red (no broken links); the memory index has no more tokens than before.
5. Commit once per repo, no push: memory repo `git -C <dir> add -A -- .` then commit "dream: <items>"; project repo: `git add` the changed lessons, docs, `nomess.json` and `.claude/rules/nomess/` one by one, then commit.
6. Delete the proposal file. Reply: `git diff --stat <before>..<after>` for each repo, the commit hashes, any item not done with its reason, and the undo command `git -C <dir> revert <commit>`.
