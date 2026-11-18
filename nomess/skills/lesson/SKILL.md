---
name: lesson
description: >-
  Record a lesson in docs/lessons/inbox.md. Argument: one sentence.
disable-model-invocation: true
argument-hint: "<the lesson in one sentence>"
---

# lesson: record a lesson

Lessons live in the repo, so coding subagents can look them up before they start. Nothing is set up in advance: the first `lessons add` creates `docs/lessons/` and `inbox.md` by itself.

## Don't record

- Anything visible from the code or git.
- Status that will go stale (progress, what some number is now): put it in the schedule or docs.
- User preferences: personal memory.
- Anything mechanically checkable ("X may only appear in Y"): write it as a `nomess.json` rule proposal for the user; once registered, run check to confirm it fires.

## Write three fields

Distill from `$ARGUMENTS` and this conversation:
- **Title**: one sentence.
- **When**: the trigger situation where it applies ("before changing a save field") + related file paths and two or three keywords, for `lessons find` to match. Not a summary of the content.
- **What**: what to do, why, source (commit hash or date); for a failure, write "how to avoid it next time".

## Write it

`${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py" lessons add "<title>" -s "<when>" -b "<what>"`, adding `--unverified` if it was not checked against the code; the script appends it to the inbox with the date, or overwrites the entry with the same title in place; never edit the inbox by hand. Then confirm with the same script `lessons find <a keyword>` that it is found, and reply to the user in one line: the title + the count from `lessons status`.
