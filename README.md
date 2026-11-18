# nomess

English | [简体中文](README.zh-CN.md)

**When several AI agents change the same repo, nomess holds them to the rules your project writes down: a check on every commit, per-folder lessons the agents load themselves, and a design-first workflow with review levels.** A Claude Code plugin; needs only Python 3.9+ and git.

## What you get

- **Checks at commit time, zero tokens.** Git hooks (`pre-commit`, `pre-merge-commit`) run your rules (regex rules or your own scripts) plus built-in checks for the cases it can decide for sure (see "Pick a size"). Commits from a human terminal are checked too. Silent when clean; when something new breaks, the commit is blocked with one line.
- **Agents recall the pitfalls of the folder they touch.** Lessons you record with `/nomess:lesson` can become path-scoped rule files (`.claude/rules/nomess/`; `/nomess:dream` proposes, you approve) that Claude Code loads only when a matching file is opened.
- **A system map generated from the code.** `docs/system-map/` is refreshed inside the commit on your main branch (`main_branch` in `nomess.json`); on feature branches it can be out of date.
- **A design-first workflow.** The `workflow` skill loads when Claude plans, dispatches or merges work: three change tiers (full / light / direct), briefs precise enough to hand to a subagent, a trial read before dispatch, three review levels (`light` / `standard` / `strict`).
- **Lessons and memory you can read, edit and commit.** Plain markdown; `/nomess:dream` tidies them as a proposal you confirm first.

## Quick start

```sh
claude plugin install nomess --marketplace penstic123-code/Nomess
```

This adds the GitHub repo as a plugin source and installs the plugin in one step (inside Claude Code: `/plugin install nomess --marketplace penstic123-code/Nomess`). It asks once which Python command to use: `python3` on macOS / Linux, `python` on Windows (`py` if that is all you have). Skip the question with `--config python=python3`; change it later in `/config`.

Then open Claude Code in your project and run `/nomess:init` (it asks questions, so it needs an interactive session; `claude -p` cannot answer them). It asks the project size and doc language (`en` or `zh-CN`), finds (or asks for) your main branch, installs the git hooks, freezes today's findings as a baseline, and prints a report: the existing findings, where the hooks live, a CI snippet. It never overwrites a file. Added to your project:

```
nomess.json            settings and check rules
AGENTS.md              entry with a generated nomess section (CLAUDE.md gets @AGENTS.md as its first line)
docs/overview.md       design overview, for humans
docs/systems/*.md      one page per subsystem (fill in the Details and Pitfalls parts yourself)
docs/lessons/          lessons library
docs/system-map/       generated, do not edit
.nomess-baseline.json  today's findings, so only new ones block
.nomess/               local cache, git-ignored
```

Large projects also get `docs/schedule.md`, `docs/ownership-map.md` and `docs/plans/`. `.gitignore` gets one line, `.gitattributes` three.

Nothing happens? Run `nomess doctor`: one line per check, with a fix for each problem.

### Pick a size

`size` in `nomess.json` sets which built-in checks and which review level are on by default. Pick the smallest that fits; anything you write in `check.builtin` or `review.level` wins over it.

| `size` | For | Built-in checks on | Review |
|---|---|---|---|
| `small` | one person, one agent at a time | D1 exact copy-paste (red), P1 swallowing every exception (red), S1 a new file over the length limit (red) | `light` |
| `medium` | a few agents, some parallel work | adds A1 subsystem import cycles (red when Python edges form it) | `standard` |
| `large` | many agents in parallel | adds C4 overlapping in-progress packages in `docs/schedule.md`, PL-DUP, PL-STALE | `standard` |

Only the sure cases block a commit; renamed clones, narrower exception handlers and cycles in other languages are reported as yellow. Re-run `/nomess:init` to move up; moving down counts as loosening (see below). `nomess check --rules` lists every rule with what it checks and what it prevents.

## Using it

| | |
|---|---|
| `/nomess:lesson "<one sentence>"` | record a lesson in `docs/lessons/inbox.md` |
| `/nomess:dream` | proposal: merge duplicates, drop stale entries, turn verified lessons into rules; `/nomess:dream execute` carries it out |
| `/nomess:review` | review the current change at the `review.level` of `nomess.json` |
| `nomess check` / `nomess map` | run the checks / regenerate the system map by hand |

Your own rules go in `check.rules`: `forbid` reports lines matching a regex, `require` reports files with no match, `cmd` fails on a non-zero exit; `red` blocks, `yellow` only reports. Regexes are JSON strings, so write `\\b` for `\b`. See [`nomess/scripts/README.md`](nomess/scripts/README.md) for every key.

```json
"check": { "rules": [
  {"id": "R1", "level": "red", "what": "no print() in src", "why": "use the logger", "glob": "src/**/*.py", "forbid": "\\bprint\\("}
]}
```

### The `nomess` command in your own terminal

`nomess` is on the PATH of Claude's shell only. In your terminal run the script directly: `python <install path>/scripts/nomess.py check` (`<install path>` is `installPath` in the output of `claude plugin list --json`; `nomess doctor` also prints where things are). Everything in this README written as `nomess ...` works that way.

### When a commit is blocked

```
nomess: 1 new red finding(s), first src/a.py:1 R1 prevents: use the logger; details: nomess check --red
```

This is the rule doing its job, not a crash (some tools prefix it with "hook failed"). Read it as file:line, rule id, what the rule prevents. Run `nomess check` for the full list, fix the code, commit again. Findings frozen at init do not block; only new ones do. If the rule is wrong for one file, add an entry with a reason to the top-level `allow` list of `nomess.json`; reviewers must look at every new `allow`.

In an emergency a person can skip the check with `git commit --no-verify` (the plugin refuses it when an agent tries). Loosening the rules themselves (removing a rule, narrowing a regex, deleting `nomess.json`) also needs `--no-verify` plus the PR label `nomess-loosen`; without the label CI fails.

## It is not a security boundary

The git hooks are a speed bump. `--no-verify` skips them; cherry-pick, rebase and am are not guaranteed to be checked; a clone that never ran init has no hooks; one working tree does not support several agents committing at once (give parallel agents a worktree each). CI is the backstop; add this to `.github/workflows/nomess.yml`:

```yaml
name: nomess
on: [pull_request, push]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: git clone --depth 1 --branch v0.9.0 https://github.com/penstic123-code/Nomess ../nomess-src
      - env:
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
          LOOSEN: ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
        run: python ../nomess-src/nomess/scripts/nomess.py check --ci --base "$BASE" $LOOSEN
```

`BASE` must be a trusted commit: the PR base, or the push's `before`. For the first push of a new branch `before` is all zeros; use the merge-base with your main branch instead.

## How it differs

Most agent-memory tools give the agent an external brain that records on its own, backed by a database, a background process, model calls or an account. nomess keeps memory as markdown in your repo, its hooks never call a model, and it covers more than memory.

| | nomess | [claude-mem](https://github.com/thedotmack/claude-mem) | [engram](https://github.com/Gentleman-Programming/engram) | [mem0](https://github.com/mem0ai/mem0) |
|---|---|---|---|---|
| Storage | markdown in your repo | SQLite + Chroma | SQLite + FTS5 | vector store |
| Runs | scripts on commit | background worker; a model compresses every tool call | single binary with MCP tools | library or service; an LLM extracts memories |
| Needs | Python, git | Bun, uv, a model source | nothing extra | LLM and embedding keys |
| Also covers | commit checks, system map, workflow, reviews | – | – | – |

Known weaknesses: lesson lookup is keyword search, so it can miss synonyms; nomess never extracts memories automatically; function-level checks support Python only.

## Requirements

Claude Code 2.1.277 or later, Python 3.9+, git 2.24+. Sized for small and medium repos: on a repo with thousands of source files the commit check currently takes several seconds (faster caching is planned for 0.9.1). `/nomess:init`, `/nomess:lesson`, `/nomess:dream` and agent commits all run scripts through Claude's shell tool, so that tool must work.

## Token cost

- **Always loaded: about 530 tokens.** About 280 for the descriptions of two skills and two subagents (check with `claude plugin details nomess`), about 250 for the nomess section (at most 12 lines) in your `AGENTS.md`. Manual commands such as `/nomess:init` cost nothing until you run them.
- **Each context that writes code: about 2,000 more** (the `lean-change` skill text). This is the main cost for a small project. Rule files load only when a matching file is opened, at most 400 tokens each.
- **Hooks: 0.** They are scripts. A blocked commit puts about 60 tokens of output in front of the agent.
- **One `/nomess:dream`:** a normal Claude session, about 95k tokens measured on a 19-page memory folder (proposal about 47k, execution about 49k).

## What it reads and writes

In your project: `nomess.json`, the generated files above, one `.gitignore` line, three `.gitattributes` lines, `.nomess/`; inside `.git/`, two hook files and a launcher (`.git/nomess-hook`), none of which are versioned. Outside it: the Python option, stored by Claude Code in `~/.claude/settings.json`; the marketplace you add is declared in your user settings; after you confirm, `/nomess:dream` edits your Claude Code memory folder, runs `git init` there if needed and commits (never pushes). It reads the `autoMemoryDirectory` setting. It does not touch `~/.claude/CLAUDE.md`, does not create `~/.claude/memory/` and does not read other projects.

Subagents: `reviewer` and `trial-reader` are read-only by instruction; their tool list includes the shell (they run `nomess` and git to look at the diff), so this is a rule in their prompt, not a sandbox.

## Security and privacy

No network access, no telemetry, no data collection. **Commands registered in `nomess.json` are executed**: `cmd` check rules and `cmd` / `py` doc generators run on commit and on `nomess check`; `review.cmd` runs on `/nomess:review`. Treat `nomess.json` like a build script and read it before working in a repo you did not write; `nomess check --no-exec` skips them.

## Turn it off, uninstall

- **Pause the Claude Code part:** `/plugin disable nomess`. The git hooks keep running.
- **Stop the commit gate on this machine:** `nomess hooks uninstall` (removes the hook files it wrote and turns the launcher into a no-op; `nomess hooks install` brings it back; delete `.git/nomess-hook` to remove it completely). `nomess hooks status` shows the current state.
- **Stop using nomess in a repo:** commit the deletion of `nomess.json`. That counts as loosening, so it needs the PR label `nomess-loosen`. Files you can then delete: `.nomess-baseline.json`, `docs/system-map/`, `docs/lessons/`, `docs/systems/`, `docs/overview.md` (and the large-project files), `.claude/rules/nomess/`, the nomess section in `AGENTS.md` (between its markers), the `@AGENTS.md` first line of `CLAUDE.md`, the `.nomess/` line in `.gitignore`, the three `.gitattributes` lines, the CI file.
- **Remove the plugin:** `claude plugin uninstall nomess`, then `claude plugin marketplace remove <marketplace name>` (see `claude plugin marketplace list`).

## VS Code extension

Sidebar for the docs, check results in the Problems panel, stale-doc count in the status bar. It calls the same script and never calls Claude. Store release is coming; until then build it from source.

## More

[Changelog](CHANGELOG.md) · [License: MIT](LICENSE) · Skill texts: [`nomess/skills/`](nomess/skills/) · Chinese translations: [`docs/zh-CN/`](docs/zh-CN/) · Questions and bugs: GitHub Issues at `penstic123-code/Nomess`. A personally maintained project; no response time is promised.

Credits: ideas from [ponytail](https://github.com/DietrichGebert/ponytail) and Google's [ReasoningBank](https://github.com/google-research/reasoning-bank); no code copied.

