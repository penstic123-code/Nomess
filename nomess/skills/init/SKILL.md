---
name: init
description: >-
  Scaffold nomess in a project, or move it to a bigger size: asks size and language, creates docs, AGENTS.md, nomess.json, installs the git hooks.
disable-model-invocation: true
---

# init: scaffold a project

Templates are in `${CLAUDE_PLUGIN_ROOT}/skills/init/templates/<lang>/` (`en` or `zh-CN`), all data. Below, `nomess.py` means `${user_config.python} "${CLAUDE_PLUGIN_ROOT}/scripts/nomess.py"`, run from the project root. Never overwrite an existing file; the only edits to existing files are the ones written below. Report skipped files.

## 1. Ask everything first, in one go

**Size**: ask exactly one question, "How many AIs change code at the same time?" Windows and subagents both count; answer by what happens at least once a month, not by the usual day.

| Answer | `size` |
|---|---|
| Only one, never in parallel | `small` |
| Now and then two or three in parallel (e.g. subagents on a job that runs for weeks) | `medium` |
| Several on most days (several windows, or packages in parallel all the time) | `large` |

**Rerun** (`nomess.json` exists): ask only the size; take everything else from it, then go to section 4.

- **Doc language**: `en` or `zh-CN`, written to `lang`; it picks the template directory.
- **git**: if `git rev-parse --show-toplevel` fails, ask whether to `git init`; if not, stop (checks and hooks need git).
- **Main branch** (`main_branch`, never guess): `git symbolic-ref --short refs/remotes/origin/HEAD` minus `origin/`; else, with no commits yet, `git symbolic-ref --short HEAD`; else ask.
- **Project name**: the repo root directory name, the `AGENTS.md` title.
- **Subsystems**: from the top-level directories and entry files, list names and path globs (a file may match only one). Empty project or unclear: ask (one part is fine).

## 2. Create, by size

| File | small | medium | large |
|---|---|---|---|
| `nomess.json`, `docs/overview.md`, `AGENTS.md` + `CLAUDE.md`, `docs/systems/<name>.md`, `docs/lessons/`, `.gitignore`, `.gitattributes` | yes | yes | yes |
| `docs/plans/archive/.gitkeep` (plans are written from `plan.md`, which is not copied) | | yes | yes |
| `docs/schedule.md`, `docs/ownership-map.md` | | | yes |

The system map `docs/system-map/` is generated at every size (small: front page only).

1. `nomess.json`: copy the template; fill in `main_branch`, `size`, `lang`, `systems`. Large: add `"owners": {"file": "docs/ownership-map.md", "builtin": "owners"}` to `docgen`. Don't write `check.builtin` or `review.level`: they follow `size`.
2. `docs/overview.md` (for humans): copy; from the code you read, write intent, how it works (one Mermaid diagram plus a few sentences) and features; no code names; keep the placeholder where you don't understand.
3. `AGENTS.md`: missing → `# <project name>`, a blank line, then `AGENTS-nomess.md`; present → append a blank line and the content of `AGENTS-nomess.md` (if a `## nomess` section exists, apply the marker rule). `CLAUDE.md`: missing → the single line `@AGENTS.md`; present without that standalone line → insert it as the first line.
4. `docs/systems/<name>.md` per subsystem from `system-page.md`, first line `# <name>`; fill the three head lines where you can.
5. `docs/lessons/`: copy `inbox.md` and `README.md`.
6. `.gitignore`: add the line `.nomess/` if missing. `.gitattributes`: add whichever of these three lines are missing (one pattern per line): `docs/system-map/** text eol=lf`, `.claude/rules/nomess/** text eol=lf`, `<lessons_dir>/inbox.md merge=union` (`lessons_dir` defaults to `docs/lessons`).
7. Medium and large: the plans directory. Large: copy `schedule.md` and `ownership-map.md`.

**Marker rule** (every `docgen` entry): `docgen` rewrites only the text between exactly one pair of `<!-- GEN:<key> BEGIN -->` / `<!-- GEN:<key> END -->` lines in the entry's file. When that file already exists: one pair → register; none → append the template's block (for `nomess`, the `## nomess` heading plus the pair) at the end and register; more than one, or the user doesn't want it changed → don't register, report it.

## 3. Wrap up

1. `nomess.py refresh` (generated sections, system map, path rules).
2. `nomess.py check --freeze`: existing debt goes into `.nomess-baseline.json`, so the first check has no red.
3. `nomess.py refresh` again (the system map front page counts the frozen entries).
4. `nomess.py hooks install`: keep its output (launcher, hook directory, or the recipe for an existing hook manager).
5. `nomess.py check` has no red, `nomess.py doctor` shows no FAIL. Red in files init created: fix; elsewhere: report. A doctor FAIL init can't fix (Python, the plugin's python option): report it with its `Fix:` line.

Don't commit. Report to the user:
- size and language; created; skipped (already existed); where the placeholders are;
- existing debt: entries per rule id in `.nomess-baseline.json`, e.g. "copy-paste 3, swallowed exceptions 2, frozen";
- hooks: the `hooks install` output; if it printed a recipe, the commits are not gated until the user wires it in;
- the CI snippet below (main branch filled in), for `.github/workflows/nomess.yml`;
- next steps: register one-entry-point rules in `check.rules` and directory strictness in `scopes`, e.g.:

```json
"check": {"rules": [
  {"id": "R1", "level": "red", "what": "rounding money only in money.py", "why": "one rounding rule", "glob": "**/*.py", "forbid": "\\bround\\("},
  {"id": "R2", "level": "red", "what": "file I/O only in storage/", "why": "one place for paths and encodings", "glob": "src/**/*.py", "forbid": "\\bopen\\("},
  {"id": "R3", "level": "red", "what": "HTTP only through http_client", "why": "one place for retries and timeouts", "glob": "src/**/*.py", "forbid": "\\brequests\\."}]},
"allow": [{"rule": "R1", "file": "src/money.py", "reason": "the one entry point"},
          {"rule": "R2", "file": "src/storage/**", "reason": "the one entry point"},
          {"rule": "R3", "file": "src/http_client.py", "reason": "the one entry point"}],
"scopes": [
  {"paths": ["src/core/**"], "smells": {"file_lines": 400, "func_lines": 50}, "review": "strict", "why": "core: mistakes are costly"},
  {"paths": ["tools/**"], "checks": {"remove": ["D1", "S1"]}, "review": "light", "why": "one-off scripts"}]
```

CI snippet:

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

## 4. Rerun: change size

- **Bigger**: in `nomess.json` change only `size` (large: also add the `owners` docgen entry); create only the missing files of the new size from section 2; leave every existing file as it is. Then section 3. Report the checks now in effect (the lines of `nomess.py check --rules` not marked "not enabled"). If `nomess.json` has an explicit `check.builtin`, it stays as written; tell the user which defaults of the new size it lacks (medium adds A1; large adds C4, PL-DUP, PL-STALE).
- **Smaller**: don't change anything. A smaller size switches checks off, which the commit gate blocks as a loosening; tell the user the person does it: edit `size`, commit with `--no-verify`, and label the PR `nomess-loosen`. Before going down to `small`, change every link that points to a system-map subpage (`files.md`, `deps.md`, ...) to point to the home page `index.md`, and commit that together with `size`; `small` deletes the subpages and the broken links would fail DOC1.
- **Same**: create only missing files, then section 3.
