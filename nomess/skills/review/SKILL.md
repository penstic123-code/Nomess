---
name: review
description: >-
  Review one change per review.level and verify each comment. Argument: optional base commit or branch.
disable-model-invocation: true
argument-hint: "[base commit or branch]"
---

# review: review one change

Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`. Run everything from the project root (the directory with `nomess.json`). The reviewer's whole input is `nomess.py review-input <base> [excerpt file]`: it compares the HEAD commit with the base, so commit the change first. It runs no project code.

## 1. Prepare

1. Base: `$ARGUMENTS` if given; otherwise `git merge-base <main_branch> HEAD`, `main_branch` from `nomess.json`. For a batch review, the merge base of the whole batch.
2. Design excerpt: only what concerns this change — its paragraphs in the plan, the owner entries it touches. Write it to `.nomess/review-excerpt.md` (`.nomess/` is not committed); for a Light change with no plan, write "none". Don't give the whole plan, the author's handback or your conclusions.
3. Run `nomess.py review-input <base> .nomess/review-excerpt.md` and keep only its first line (`| head -n 1`; PowerShell `| Select-Object -First 1`): the review level (`review.level`). If the line ends with `[must-review]`, the review input has a must-review section (a new `allow`, a new freeze, B1/B2 or a loosening).

## 2. Review or not

| Level | Per package (one package's diff) | Per batch (a batch's combined diff) |
|---|---|---|
| `off` | No review | No review |
| `light` | No review (light-process changes: one module only, callers unaffected, are never reviewed alone) | Review, skipping docs, config, tests |
| `standard` | Review logic code; no review if only docs, config, templates changed, or if it is a light-process change (one module only, callers unaffected) | Review |
| `strict` | Review all, light-process changes included | Review |

At `off`, nothing is reviewed, not even the items below (loosening still needs the `nomess-loosen` PR label). Always review at any other level: a first line marked `[must-review]` (check this first, before the table); changes outside the brief (even one line); Medium-process changes (a system's external behavior changes but stays within that system; reviewed alone once at light, standard and strict); Full-process changes (file or save format, interface, execution timing or data owner); commits that add an `allow` (listed in the must-review section of the review input); System-process work: review each milestone's combined diff once.

If no review is due, tell the user "no review under `<level>`" with the reason, and stop.

## 3. Choose the reviewer (the cheapest that suffices)

- `review.cmd` is set in `nomess.json`: everything that needs review goes to it; no subagent. Run `nomess.py review-input --cmd <base> .nomess/review-excerpt.md` from the project root: it pipes the checklist and the review input to `review.cmd` through stdin only (never spliced into a shell command) and prints its output.
  A non-zero exit or a timeout is reported as "review failed" (with stderr), never as "no problems found".
- Not set: dispatch the `nomess:reviewer` subagent.
  - Ordinary code: sonnet by default. Heavy logic, trade-offs, cross-system: specify `model: opus`; under `strict`, anything with trade-offs gets the strongest model. No haiku: it misses too much logic to save anything.
  - The prompt gives only: the base, the excerpt path `.nomess/review-excerpt.md`, and one sentence on what the change is meant to do. The reviewer runs `review-input` and reads the checklist itself.
  - Batch review: add "only look for semantic conflicts between packages".

## 4. Verify

For each comment received, re-read the code it points at and write "accepted" or "rejected + reason". Reviewers make mistakes too. List items marked "suggest making this a check rule" separately for the user.

## Report (to the user)

One table: comment (file:line + one sentence) | accepted / rejected | reason. Last line: who fixes the ones to change. This skill doesn't change code.
