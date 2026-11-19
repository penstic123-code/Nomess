---
name: init
description: >-
  Enable nomess in this repo, or move it to a bigger size: runs `nomess init --auto` and reports what it did.
disable-model-invocation: true
argument-hint: "[--size small|medium|large] [--lang en|zh-CN] [--docs standard|free|custom]"
---

# init: enable nomess

`nomess` below means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root. Usually nothing needs doing: the session hook asks the AI to run the same command before the first file change.

1. Run `nomess init --auto --lang <en|zh-CN> [--size <size>] [--docs <docs>]`. When there is no `nomess.json` yet and `$ARGUMENTS` names no `--docs`, first ask the user in one sentence how docs should be managed: the standard 7 types (`standard`), no fixed places, good for experiments (`free`), or their own list of types (`custom`, edited in `nomess.json` afterwards); `standard` if they don't care. An enabled repo is not asked. `--lang` is the language the user writes in; pass `--size` only if `$ARGUMENTS` names one (default `small`; how many AIs change code at the same time: one → `small`, two or three now and then → `medium`, several on most days → `large`). It asks nothing, only fills in what is missing (rerunning is harmless), and doesn't commit.
2. Exit 2: report its message. Detached HEAD → ask the user for the main branch, check out a branch and run again. Not a git repository → stop (checks and hooks need git; don't `git init` for the user). A smaller `--size` → the person does it: edit `size` in `nomess.json`, commit with `--no-verify`, label the PR `nomess-loosen`; before going down to `small`, point links to system-map subpages at `index.md` (`small` deletes the subpages).
3. Report its last line to the user in one or two sentences: files changed, existing findings frozen, whether commit checks are wired (if not, `nomess hooks install` prints the recipe for their hook manager). After a size change also name the checks now in effect (lines of `nomess check --rules` not marked "not enabled"; medium adds A1, large adds C4, PL-DUP, PL-STALE). To switch nomess off in this repo: `nomess off`.

Next steps worth suggesting: one-entry-point rules in `check.rules` with `allow`, and per-directory strictness in `scopes` (format in `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`); and CI, `.github/workflows/nomess.yml` with the main branch filled in:

```yaml
name: nomess
on: [push, pull_request]
jobs:
  nomess:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - run: git clone --depth 1 https://github.com/penstic123-code/Nomess "$RUNNER_TEMP/nomess"
      - run: |
          base="${{ github.event.pull_request.base.sha || github.event.before }}"
          case "$base" in ""|0000000000000000000000000000000000000000) base=$(git merge-base origin/<main_branch> HEAD);; esac
          python3 "$RUNNER_TEMP/nomess/nomess/scripts/nomess.py" check --ci --base "$base" ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
```
