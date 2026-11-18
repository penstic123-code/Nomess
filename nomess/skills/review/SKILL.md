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
3. Run `nomess.py review-input <base> .nomess/review-excerpt.md` and keep only its first line (`| head -n 1`; PowerShell `| Select-Object -First 1`): the review level, the strictest among the changed files, and the file that set it. If the line ends with `[must-review]`, the review input has a must-review section (a new `allow`, a new freeze, B1/B2 or a loosening).

## 2. Review or not

| Level | Per package (one package's diff) | Per batch (a batch's combined diff) |
|---|---|---|
| `off` | No review | No review |
| `light` | No review | Review, skipping docs, config, tests |
| `standard` | Review logic code; no review if only docs, config, templates changed | Review |
| `strict` | Review all | Review |

At `off`, nothing is reviewed, not even the items below (loosening still needs the `nomess-loosen` PR label). Always review at any other level: a first line marked `[must-review]` (check this first, before the table); changes outside the brief (even one line); Full-process changes (file or save format, interface, execution timing or data owner); commits that add an `allow` (listed in the must-review section of the review input).

If no review is due, tell the user "no review under `<level>`" with the reason, and stop.

## 3. Choose the reviewer (the cheapest that suffices)

- `review.cmd` is set in `nomess.json`: everything that needs review goes to it; no subagent. Save the snippet below as a temporary `.py` and run, from the project root, `${user_config.python} <it> <base> "${CLAUDE_PLUGIN_ROOT}"`. Content goes only through stdin, never spliced into a shell command.
  ```python
  import json, os, subprocess, sys
  from pathlib import Path
  base, plugin = sys.argv[1], sys.argv[2]
  argv = json.loads(Path("nomess.json").read_text("utf-8-sig"))["review"]["cmd"]
  env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")  # Python reviewers use UTF-8 I/O; others must use UTF-8 themselves
  ri = subprocess.run([sys.executable, str(Path(plugin, "scripts/nomess.py")), "review-input", base, ".nomess/review-excerpt.md"],
                      capture_output=True, text=True, encoding="utf-8", env=env, check=True).stdout
  checklist = Path(plugin, "skills/lean-change/review-checklist.md").read_text("utf-8")
  try:
      r = subprocess.run(argv, input=checklist + "\n\n" + ri, capture_output=True, text=True, encoding="utf-8", env=env, shell=False, timeout=600)
  except subprocess.TimeoutExpired:
      sys.exit("review failed: no response within 600 seconds")
  if r.returncode:
      sys.exit("review failed (exit code %d): %s" % (r.returncode, r.stderr))
  print(r.stdout)
  ```
  A non-zero exit or a timeout is reported as "review failed" (with stderr), never as "no problems found".
- Not set: dispatch the `nomess:reviewer` subagent.
  - Ordinary code: sonnet by default. Heavy logic, trade-offs, cross-system: specify `model: opus`; under `strict`, anything with trade-offs gets the strongest model. No haiku: it misses too much logic to save anything.
  - The prompt gives only: the base, the excerpt path `.nomess/review-excerpt.md`, and one sentence on what the change is meant to do. The reviewer runs `review-input` and reads the checklist itself.
  - Batch review: add "only look for semantic conflicts between packages".

## 4. Verify

For each comment received, re-read the code it points at and write "accepted" or "rejected + reason". Reviewers make mistakes too. List items marked "suggest making this a check rule" separately for the user.

## Report (to the user)

One table: comment (file:line + one sentence) | accepted / rejected | reason. Last line: who fixes the ones to change. This skill doesn't change code.
