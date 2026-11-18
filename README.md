<p align="center"><img src="docs/logo.svg" width="96" alt="nomess logo"></p>

# nomess

English | [简体中文](README.zh-CN.md)

nomess is a Claude Code plugin that keeps a shared codebase maintainable and cuts rework as multiple AI agents change it over time. It has six parts. Agents investigate before writing code. A workflow puts design before delegation, and a commit gate enforces project rules. The other parts are a system map generated from code, memory and lessons, path-scoped rules, and code smell detection. The commit checks run as Python scripts in Git hooks, with zero model calls or token use. The plugin requires only Python 3.9 and Git.

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

## What day-to-day use looks like

After installing the plugin, run `/nomess:init` in an interactive Claude Code session for your project. Choose the project size, documentation language, and main branch, then set up the commit checks. Edit, stage, and commit as usual. If an agent copies a long enough block of validation code into another file, the commit stops. The message shows where both copies are:

```text
nomess: 1 new red finding(s), first src/import.py:42 D1 src/import.py lines 42-58 repeats src/validate.py lines 10-26 (108 tokens, identical); details: nomess check --red
```

The agent can read both locations, make the import flow call the existing validator, then stage and commit again. Passing checks are usually silent. Commands like `/nomess:…` go into Claude Code. Commands like `nomess …` run the script. In your own terminal, you can also run `python <plugin install path>/scripts/nomess.py` with the same arguments.

## 1. Write less code by checking first

Suppose two upload entry points both store a blank filename as an empty string. An agent sees an error from one entry point and adds a check there. A third entry point can bring the same bug back. `lean-change` asks the agent to find the callers and trace the data to see which shared step should validate it.

`lean-change` is a skill, a set of instructions Claude Code can load for relevant tasks. It loads when you add a feature, fix a bug, refactor, or choose a dependency. Describe the task as usual. The agent finds the callers, data, configuration, and documentation the change touches, reads the files it will edit, and runs `nomess lessons find <路径或关键词>` to look up to three relevant lessons.

The skill asks a series of questions in order. Do we need this feature? Does the repository already have it? Can the standard library or an installed dependency handle it? For protocols, concurrency, or unfamiliar third-party APIs, consult reliable sources first. If those options fall short, write enough code to solve the problem. When handing off the change, the agent reports where it found a solution and how it verified the change.

That sequence gives the agent more to work with than “write as little code as possible.” Moving validation to the shared layer might mean changing two call sites, and both entry points then use the same logic. Optimizing for a smaller diff can leave the check in the wrong place.

## 2. Workflow and commit gate

Suppose you add a field to a save file. One agent changes the write format while another adds a default when loading. Both changes can pass their own tests, yet together they can overwrite a value from an older save. `workflow` coordinates changes where agents need to agree on behavior up front. The commit gate handles checks such as catching a call that the project forbids in a particular module.

Claude loads `workflow` when it plans, delegates, reviews, or merges work. Small edits to comments or docs can go straight in. A self-contained fix uses a lightweight workflow. Changes to interfaces, save formats, execution order, or data ownership use the full workflow. Decide who reads, who writes, and when writes happen, then review the design. Before delegating, have a subagent that missed the discussion read the brief and flag anything it would need to know. Each parallel task gets its own Git worktree, a separate working directory for the same repository. Use `/nomess:review` to manually review committed changes.

Git runs the gate. `pre-commit` runs before Git records a regular commit. `pre-merge-commit` runs before Git creates an automatic merge commit. The script reads the files, configuration, and baseline staged for commit and compares them with the tree at `HEAD`. If you use `git add -p` to stage half a change, built-in checks use the file version containing just that half. Project-defined `cmd` checks read from disk. If a tracked file has unstaged changes, the hook skips the command and tells you to run it in CI.

Project rules live in `check.rules`. `forbid` looks for banned patterns. `require` checks that files contain a required pattern. `cmd` uses the exit code of a project command. Red findings block the commit. Yellow findings are there for people to review. If a file needs an exception, record the rule, file, and reason in the top-level `allow`. New exceptions appear in the material reviewers receive.

Since Git runs the checks, they also run when someone commits from a terminal, with no model calls. A person can use `git commit --no-verify` in an emergency. Before common shell commands run, the Claude Code plugin hook blocks agents from using that option or changing `core.hooksPath` to bypass checks. Teams can also run `nomess check --ci --base <可信提交>` in CI to compare `HEAD` with the PR’s target commit. If the project deliberately relaxes a rule, a person approves the change, adds the `nomess-loosen` label to the PR, and configures CI to pass `--allow-loosen` when that label is present.

## 3. System map and automatically updated docs

Before removing `billing`, you want to know which modules still import it. A hand-drawn architecture diagram can explain why the system is split up that way. Six months later, it can be hard to tell from that diagram who still calls what. `docs/system-map/index.md` gives you a starting point generated from the code. Larger projects also get file, dependency, and custom extraction tables.

Run `nomess map` to rebuild the system map manually. The script starts with Git’s file list and groups files using the `systems` configuration. By default, it groups them by top-level source directory. It turns imports that resolve to files in the repository into dependency edges, then rolls them up to subsystem dependencies. It extracts Python imports from the syntax tree and approximates imports in some other languages using text patterns. Projects can also define regular expressions in `map` to extract things that follow a consistent convention. For example, calls like `EMIT("order.paid")` can feed an event table. Dynamically constructed event names fall outside that table’s coverage.

To insert an event table into a hand-written document, register a generated section named `events` in `docgen` and add these two markers to the document:

```markdown
<!-- GEN:events BEGIN -->
<!-- GEN:events END -->
```

`nomess docgen` replaces only the content between the markers. Eligible regular commits on the main branch automatically refresh the system map, rule files, and document sections that can be generated from the staged snapshot. The hook adds the generated changes to the proposed commit for checking and stages them for that commit only after the checks pass. It skips generated files with unstaged edits. `cmd` and `py` generators run on manual refresh. The automatic merge hook only checks. Generated files on feature branches can lag behind, so run `nomess refresh` when you need to update them.

People document design trade-offs and pitfalls they’ve encountered. The script rebuilds the inventories it can get from the code. Change an import and the next refresh updates the dependency map.

## 4. Memory and lessons

After you fix an incident, Git can show which lines changed. It’s harder for the next person to learn why adding retries to checkout requests caused duplicate charges. Keep that information in the repository so people can look it up alongside the code.

Record a lesson with `/nomess:lesson "结算重试必须复用原请求的幂等键"`. The plugin gives it a title and records when to look it up, what to do, why it matters, and what evidence supports it. The script dates the entry and writes it to `docs/lessons/inbox.md`. A matching title updates the existing entry. Earlier wording stays available in Git history. Entries that haven’t been checked against the code are marked unverified. `lessons find` searches these entries by path and keyword. Including `src/billing/` and “retry” in the entry makes it easier to find than a general note about checkout pitfalls.

As lessons accumulate, run `/nomess:dream`. It checks the lesson collection and, when it can locate it, the current project’s Claude Code memory directory. It looks for duplicate titles, broken links, and pages over budget, then checks the facts in its proposal against the code and Git history. After reading the proposal, run `/nomess:dream execute` to apply it. Use `execute strike 2 5` to drop items 2 and 5. The cleanup merges duplicates, removes outdated guidance, and proposes turning lessons that keep coming up into rules. It verifies the result and leaves a record in repositories where it can commit.

These notes are short, plain Markdown files. You can review the diffs and carry the notes across branches. For a question like “Which lesson should I read before changing checkout retries?”, a path and a keyword narrow the search enough. There’s no vector database to maintain. A lesson phrased with different words can slip past the search.

## 5. Path-scoped rules

“Reuse the original idempotency key when retrying checkout” matters in `src/billing/`. An agent changing only the homepage styles has little use for it, and reading it takes up context. If every lesson goes into the project’s main instructions, the rules that apply everywhere get harder to find.

`dream` can propose promoting a verified lesson that applies repeatedly to a path-scoped rule. You can also write one in the pitfalls section of a subsystem’s documentation page. The source entry needs a verified status, path patterns, and a one-sentence rule. Drafts in `inbox.md` are skipped. Run `nomess rules` to group entries with the same set of paths into a single file under `.claude/rules/nomess/`. The filename comes from a hash of those paths. The `paths` field in the header tells Claude Code when to load the rule:

```yaml
---
paths:
  - "src/billing/**"
---
```

Claude Code loads the rule when it reads a matching file. If all you have is a few lines of `grep` output, open the file to bring the rule into context. Each rule links to its source entry so you can read the full reasoning when the short version isn’t enough.

Path-scoped rules work well for conventions that require judgment, such as choosing which request’s key to reuse on a retry. A requirement like “only this module may call the low-level write function in billing code” can go into the commit checks. The script applies the same condition every time.

## 6. Code smell detection and the ratchet

An old repository might already have three copies of a block of code. If installing a tool means cleaning them all up, even a small bug fix has to wait. If the tool ignores duplication entirely, a fourth or fifth copy can slip in. During setup, nomess runs `nomess check --freeze` to record existing findings in `.nomess-baseline.json`. It uses that list to tell which problems are new and which have grown. Run `nomess check --rules` for rule descriptions and `nomess check --all` to see existing findings too.

| Check | What the script looks for |
| --- | --- |
| D1 Duplicate code | A sufficiently long sequence of identical tokens across files is red. A match found only after normalization is yellow. |
| P1 Swallowed exceptions | For Python, the script uses the syntax tree to see what an exception handler catches and what it does. Catching all exceptions and doing nothing, for example with `pass`, is red. Swallowing a specific exception or leaving a JS/TS `catch` empty is yellow. |
| P2, P5 Patch traces | Counts markers like `TODO` and `hack` and looks for names like `_v2` and `_old` in files and definitions. Findings are yellow. |
| S1, S2 Length | Counts nonblank lines in a file or uses Python’s syntax tree to get the first and last lines of a function. New or worsening findings over the configured limit can be red. |
| A1 and `arch` architecture constraints | Rolls up imports into a subsystem graph. A cycle made entirely of Python import edges is red. A cycle that depends on approximate import extraction is yellow. Projects can also define constraints such as forbidden dependency directions or a single owner for writes. |
| C4 Parallel scheduling | Two active tasks that will edit the same file, or a task that starts before a prerequisite has merged, trigger red. Overlap inferred only from wildcard prefixes triggers yellow. |
| PL-DUP, PL-STALE Documentation | Repeated text across documents and stale paths or subsystem names in unarchived plans are yellow. |

D1 avoids comparing every file in full with every other file. It removes whitespace and comments it recognizes, then splits the code into tokens. It hashes each sequence of 25 consecutive tokens and picks the smallest hash in each sliding window of 26 hashes as a fingerprint. When two files share a fingerprint, the script goes back to the original token sequences and checks outward in both directions to measure the actual match. One pass keeps the tokens as written. Another normalizes identifiers and literals by type, so renaming variables can still leave a detectable copy. The script skips fingerprints shared by too many files so boilerplate doesn’t slow down every commit.

The baseline identifies findings by rule ID, original color, path, and characteristics of the finding itself. Line numbers only appear in messages. If a file already has two frozen red P1 findings, a third counts as new. Metrics such as length are compared with their frozen values. Growth counts as a regression once it exceeds the configured tolerance. After fixing old findings, run `nomess check --tighten` to remove entries for resolved findings and lower recorded values. Once that allowance is gone, the check catches the same problem if it comes back. That’s the ratchet.

B1 prevents hiding findings in the baseline. Hand-editing the file cannot increase an existing rule’s allowance. A first freeze applies only to rules that the baseline hasn’t enabled, that ran in the current check, and that support freezing. The recorded findings must also match the current full scan. B2 catches changes that weaken the checks. It compares both configurations with defaults filled in. Removing checks, raising managed thresholds, lowering the review level, changing the baseline location, or deleting `nomess.json` all trigger it. Freezing lets teams adopt checks without cleaning up the whole repository first. B1 and B2 keep a change from weakening the checks it has to pass.

## How the six parts work together

Suppose checkout and a background recovery job both write to the ledger. After fixing the incident, you use `/nomess:lesson` to record what happened and which two entry points were involved. `dream` verifies the lessons. One says to reuse the original request’s idempotency key on a retry. The agent needs to read the surrounding code to apply it, so it becomes a path-scoped rule for billing. The other says that only the ledger module may call the low-level write function. You can enforce it with a red `forbid` rule and record a justified exception for the file that legitimately writes to the ledger.

Later, someone asks an AI agent to add batch recovery. `lean-change` has it find the existing write entry point first. When it reads the file, the path-scoped rule reminds it to keep the idempotency key. The system map helps it trace the dependency between billing and the ledger. If batch recovery also changes who owns writes, `workflow` has the coordinator decide who writes to the ledger before assigning tasks. Even if the agent overlooks the earlier guidance, the Git hook blocks the commit if a staged file in the restricted paths calls the low-level write function directly.

## Choosing a project size and adjusting the defaults

`size` selects a set of defaults. If it’s just you and one agent at a time, start with `small`. It enables D1, P1, and S1 and uses `light` review. When several agents start working in parallel, `medium` adds A1 and raises review to `standard`. `large` adds C4, PL-DUP, and PL-STALE. It also uses a schedule to track tasks and the files each can edit, and an ownership map to record who is responsible for shared data.

This configuration keeps the four checks from `medium`, adds a function length check for hand-written payment code, and raises review to `strict` for changes that touch those files:

```json
{
  "format": "nomess/1",
  "main_branch": "main",
  "size": "medium",
  "lang": "en",
  "check": { "builtin": ["D1", "P1", "S1", "A1"] },
  "scopes": [
    {
      "paths": ["src/payments/**"],
      "why": "payment changes get a full review",
      "checks": { "add": ["S2"] },
      "smells": { "func_lines": 60 },
      "review": "strict"
    }
  ]
}
```

An explicit `check.builtin` list takes over from the size preset. `scopes` can add or remove individual file checks by path, adjust severity and thresholds, and set the review level. When several scopes match, more specific paths override settings one at a time. Top-level settings control checks that look at the entire tree, such as A1 and C4.

`off` turns review off entirely. `light` usually reviews only the combined change and skips docs, configuration, and tests. `standard` also reviews logic changes in individual work packages. `strict` reviews every package. When review is enabled, separate criteria determine whether to require it for changes that use the full workflow, go beyond the brief, or add exceptions. When a change touches multiple directories, the strictest level applies. If the project’s `AGENTS.md` or `CLAUDE.md` already specifies how to check briefs, test, or review, follow the project’s instructions.

`nomess status --suggest` lists the reasons to move up or down a size, such as recent merges and file overlap, the number of subsystems, a backlog of lessons, or a stretch with one author and no parallel merges. A person decides whether to act on the suggestion. To move up, rerun `/nomess:init` and check any explicit list of enabled checks. If moving down disables checks or lowers the review level, follow the project’s approval process for relaxing rules.

## What it doesn’t do

The commit gate enforces working agreements. Permissions and protected CI provide the security boundary. Set up local hooks in each new clone. Fast-forward merges, rebases, and cherry-picks need coverage beyond the local hooks.

The system map can extract inventories from code. The project team writes down why the system is designed that way and what trade-offs it makes. The nomess scripts run locally without network access or telemetry, and commit checks make no model calls. `dream` and review run in a Claude Code session. Custom commands registered in `nomess.json` run as configured.
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
      - run: git clone --depth 1 --branch v0.9.1 https://github.com/penstic123-code/Nomess ../nomess-src
      - env:
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
          LOOSEN: ${{ contains(github.event.pull_request.labels.*.name, 'nomess-loosen') && '--allow-loosen' || '' }}
        run: python ../nomess-src/nomess/scripts/nomess.py check --ci --base "$BASE" $LOOSEN
```

`BASE` must be a trusted commit: the PR base, or the push's `before`. For the first push of a new branch `before` is all zeros; use the merge-base with your main branch instead.

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

