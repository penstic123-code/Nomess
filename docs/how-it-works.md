# How nomess works

[简体中文](how-it-works.zh-CN.md)

nomess is a Claude Code plugin that keeps a shared codebase maintainable and cuts rework as multiple AI agents change it over time. It has six parts. Agents investigate before writing code. A workflow puts design before delegation, and a commit gate enforces project rules. The other parts are a system map generated from code, memory and lessons, path-scoped rules, and code smell detection. The commit checks run as Python scripts in Git hooks, with zero model calls or token use. The plugin requires only Python 3.9 and Git.

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