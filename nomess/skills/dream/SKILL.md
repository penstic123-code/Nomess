---
name: dream
description: >-
  Tidy lessons, docs and memory as one undoable commit. Invoke when the session hook asks (argument "auto") or the user asks to tidy docs or memory; "apply N…" runs items of .nomess/dream-notes.md.
argument-hint: "[auto | apply N…]"
context: fork
model: sonnet
---

# dream: tidy lessons, docs and memory

`nomess` below means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root. Use only `nomess` commands and Read, Grep, Edit, Write: those run without a permission prompt. Never run `git` or other shell commands yourself (they prompt); to check history use `nomess dream git-log <word>`. Field names below are the English ones; in a `zh-CN` project write the Chinese ones.

## A. Tidy (argument empty or `auto`; both the same)

1. `nomess dream begin`. Exit 3 (another tidy holds the lock): reply with its line and stop. It prints the work list, the worktree, the memory directory (if "not located": tidy the project only) and where notes go.
2. Work through the list with the actions below. Change files only inside that worktree (its path + the repo-relative path) and the memory directory, never in the main checkout. Read only what the list names; verify against the code in the worktree with Read, Grep and `nomess dream git-log <word>`.
3. `nomess dream land`: it checks the run and lands it on the current branch, or discards the whole run and says why. Reply with exactly the line it prints. Don't fix and retry a discard. To give up midway: `nomess dream abort`.

Moving or deleting a file: `nomess dream mv <old> <new>` / `nomess dream rm <path>` (paths relative to the worktree, or absolute paths in the memory directory; exit 2 means refused: leave the file and write a note).

## B. Actions, by work-list kind

Lessons (files in the lessons directory of the worktree; an entry is `## Title` plus `Key: value` lines):
- **inbox**: move each entry into the topic page it belongs to, or a new topic page `<lessons dir>/<topic>.md`, or delete it; then remove it from `inbox.md`. If `<lessons dir>/README.md` does not exist, copy `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/docs/lessons/README.md` there; if `nomess.json` has no `lessons-index` docgen entry, registering it is a note.
- **near-duplicate titles**: merge into one entry. When two conflict, keep the true one; old wording stays in git history.
- **unverified**: check against the code. True → `Status: verified`; false → rewrite or delete. An entry with `Source: external …` is never verified by you and keeps that line (land discards the run otherwise): its verification is a note.
- **Paths and rules**: a verified entry that recurs gets `Paths:` (copy the paths it already covers; don't widen) and `Rule:` (at most 25 words / 40 CJK characters).
- **missing aliases**: give the entries you touch an `Aliases:` line, comma separated: Chinese and English, common wordings, abbreviations.
- **doc gaps** (titles starting `Doc gap:` / `文档缺口:`): sum them up as one note proposing a registered doc type or a new fixed section of the system page; delete them once noted.

Docs (only the project doc root, the lessons directory, existing developer docs and the generated part of `AGENTS.md` are writable; land discards anything else):
- **plans** (PL-DUP, PL-STALE, PLN2): the same thing written twice → merge into one, delete the other and fix links. An outdated plan → move it to `<docs_root>/plans/archive/YYYY-MM-DD-<name>.md`, set `Status: superseded` and `Superseded-by:`.
- **schedule rows already merged**: move each row into the change log at the end of the plan it belongs to; the schedule keeps only unfinished rows.
- **DOC4 misplaced / stray .md**: move a page whose type is clear into that type's location and fix links; merge duplicates, archive outdated ones. One that fits no type stays where it is (the docs index lists it as unsorted) and gets a note proposing a new doc type.
- **DOC5 orphans**: link them from the page they belong under, or merge them away.
- **DOC6 too long**: the page becomes a summary page (what it is, the key points, which page to read next) and details move by topic into sub-pages in the same folder (`systems/render.md` → `systems/render-shadows.md`), linked from it. No new directory level. A system page keeps its four fixed headings on the summary page; a sub-page of a system page also starts with the three head lines (`What:` / `Why:` / `Works with:`), or DOC3 warns.
- **stale references** (a path that no longer exists): project docs → fix or delete the sentence against the code; developer docs → fix in place (never create, delete or move them); public docs → a note only.
- **memory over budget**: merge, shorten, delete; a project fact moves into the matching docs page and memory keeps one link line. Keep the index one line per topic `[topic](file) — when to use` and fix `[[…]]` links.

Write as things are now: replace old wording, never append "update: …".

## C. Notes: what a person decides

Write these to `.nomess/dream-notes.md` inside the worktree, one numbered line each (land appends them to the main checkout's file): anything that changes `nomess.json` (check rule, `arch` entry, threshold, doc type, docgen entry); verifying an external-source entry; a deletion you are unsure of; a new doc type; a public doc that may be stale.

## D. `apply N…`

Carry out items N… of `.nomess/dream-notes.md` in the main checkout (no worktree, no `begin` / `land`); here `nomess.json` may change (format in `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`). An external-source entry becomes verified only if the code confirms it: then drop its `Source:` line. A new rule or `arch` entry that makes `nomess check` red is dropped and reported, never frozen; delete a lesson once its rule is registered. Then `nomess refresh` and `nomess check`, remove the done lines from the notes, don't commit, and reply in one line: what was done, what was not and why. Raising a threshold is a loosening the commit gate blocks: say the person commits it.
