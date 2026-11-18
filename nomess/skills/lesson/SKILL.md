---
name: lesson
description: >-
  Record a lesson in the lessons inbox. Argument: one sentence.
disable-model-invocation: true
argument-hint: "<the lesson in one sentence>"
---

# lesson: record a lesson

Lessons live in the repo, so coding subagents can look them up before they start; the first `lessons add` creates the lessons directory and `inbox.md`.

## Don't record

- Anything visible from the code or git.
- Status that will go stale (progress, what some number is now): put it in the schedule or docs.
- User preferences: personal memory.
- Anything mechanically checkable ("X may only appear in Y"): write it as a `nomess.json` rule proposal for the user; once registered, run check to confirm it fires.

## Write four fields

Distill from `$ARGUMENTS` and this conversation:
- **Title**: one sentence.
- **When**: the trigger situation where it applies ("before changing a save field") + related file paths and two or three keywords, for `lessons find` to match. Not a summary of the content.
- **What**: what to do, why, source (commit hash or date); for a failure, write "how to avoid it next time".
- **Aliases** (always): other names someone would search for, comma separated, Chinese and English, common wordings and abbreviations ("存档, save, persistence").

A **doc gap**: something worth writing down has no home in any doc type (the nomess section of `AGENTS.md` lists them), or information you needed is written nowhere. Record it as a lesson whose title starts with `Doc gap:` (`文档缺口:` in a `zh-CN` project); the automatic tidy turns these into a proposal for the person.

## Write it

`${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py" lessons add "<title>" -s "<when>" -b "<what>" -k "<aliases>"`, adding `--unverified` if it was not checked against the code, and `--external "<URL or file>"` if it was learned from a web page, someone else's doc, tool output or any file outside this repo's history (only what you found by changing code yourself goes without it). An entry with the same title is overwritten in place. Never edit the inbox by hand. Then confirm with the same script `lessons find <a keyword>` that it is found, and reply to the user in one line: the title + the count from `lessons status`.
