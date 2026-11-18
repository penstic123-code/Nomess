---
name: review
description: >-
  Review one change per review.level and verify each comment. Argument: optional base commit or branch.
disable-model-invocation: true
argument-hint: "[base commit or branch]"
---

# review: review one change

Reviewers make mistakes too: re-read the code behind every comment before accepting it (section 4). The reviewer sees only the diff and a design excerpt, never the author's handback or your conclusions.

Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root. The reviewer's whole input is `nomess.py review-input <base> [excerpt file]`: it compares HEAD with the base, so commit the change first.

## 1. Prepare

1. Base: `$ARGUMENTS` if given; otherwise `git merge-base <main_branch> HEAD` (`main_branch` from `nomess.json`). For a batch, the merge base of the whole batch.
2. Design excerpt: only what concerns this change (its paragraphs in the plan, the owner entries it touches), written to `.nomess/review-excerpt.md`; "none" for a Light change with no plan.
3. Run `nomess.py review-input <base> .nomess/review-excerpt.md` and keep only its first line (`| head -n 1`; PowerShell `| Select-Object -First 1`): the review level. A trailing `[must-review]` means the script found items that are always reviewed (a new `allow` or `doc_types` entry, a new freeze, a loosening, L6).

## 2. Review or not

At `off`, nothing is reviewed (loosening still needs the `nomess-loosen` PR label). At any other level, always review: a first line marked `[must-review]`; changes outside the brief (even one line); Planned and Full changes (once per package); System-tier work (each milestone's combined diff once). Otherwise:

| Level | Per package | Per batch (combined diff) |
|---|---|---|
| `light` | No review | Review, skipping docs, config, tests |
| `standard` | Review logic code; not Light changes or changes to only docs, config, templates | Review |
| `strict` | Review all, Light changes included | Review |

If no review is due, tell the user "no review under `<level>`" with the reason, and stop.

## 3. Choose the reviewer (the cheapest that suffices)

- `review.cmd` set in `nomess.json`: run `nomess.py review-input --cmd <base> .nomess/review-excerpt.md`; it feeds the checklist and input to `review.cmd` and prints its output. If it reports a failure, tell the user "review failed", never "no problems found".
- Not set: dispatch the `nomess:reviewer` subagent.
  - Ordinary code: sonnet. Heavy logic, trade-offs, cross-system: `model: opus`; under `strict`, anything with trade-offs gets the strongest model. No haiku: it misses too much logic to save anything.
  - The prompt gives only the base, the excerpt path and one sentence on what the change is meant to do.
  - Batch review: add "only look for semantic conflicts between packages".

## 4. Verify

For each comment, re-read the code it points at and write "accepted" or "rejected + reason". List items marked "suggest making this a check rule" separately for the user.

## Report (to the user)

One table: comment (file:line + one sentence) | accepted / rejected | reason. Last line: who fixes the ones to change. This skill doesn't change code.
