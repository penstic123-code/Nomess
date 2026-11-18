# How nomess works

[简体中文](how-it-works.zh-CN.md)

This is a tour of what each part of nomess does, why it is built the way it is, and how it works underneath. For installation and commands, see the [README](../README.md).

## The problem

One AI changing code is manageable. Several AIs changing the same repository for weeks is how codebases quietly rot. The reasons are concrete: each agent sees only its own task. It doesn't know that another agent wrote the same helper three days ago, that saves are supposed to go through one module only, or what went wrong last week. So a second entry point appears for the same job, the same logic gets pasted into a third file, and a bug fix lands as a special case at the symptom instead of at the cause.

Each step looks reasonable on its own. Together they add up to a mess. Rework comes from the same place: a change collides with another system, and nobody notices until merge time or runtime.

nomess takes a simple approach. Write the project's rules down. Let scripts check the mechanical ones on every commit. Leave the rest to a workflow and to review. Hand agents what the project has already learned, at the moment they need it.

## Design principles

A few ideas run through everything:

- **If a script can check it, don't rely on the AI remembering it.** Prompts get ignored and get compressed away in long sessions; a git hook runs on every commit. The firmest parts of nomess are scripts, not prose.
- **Hooks cost zero tokens.** Every check is a Python script that never calls a model. A commit takes a second or two longer and costs nothing.
- **Only block what is new.** Problems already in the codebase are recorded in a baseline, so you don't have to pay off old debt all at once. Only new and worsening problems block a commit.
- **Everything is markdown and JSON.** Lessons, memory, the system map and configuration are plain files you can read, edit and version. No database, no background service, no network.
- **Small projects stay light.** A one-person, one-agent project gets the three most certain checks and little else. More switches on as the project grows.

The plugin needs only Python 3.9 and git, and behaves the same on Windows, macOS and Linux.

## The six parts

### ① Write less code, look before you write

A skill (`lean-change`) loads before the AI writes code, fixes a bug or designs something. It walks a decision ladder: can this be avoided altogether? Is there already a function or convention in the repo? Does the standard library or a mature open-source project already do it? Only then write it yourself, and write the smallest complete version. When unsure, check the official docs or an existing implementation first and note the source.

It comes with a review checklist for diffs: bugs, over-engineering, patch-style fixes, duplication and scatter, coupling, out-of-scope edits, wrongly removed validation. Every finding must cite a file and line, and the reviewer re-reads that line before reporting it.

### ② A workflow that prevents mess

A second skill (`workflow`) loads when the AI plans, dispatches work or merges. Its core is sorting changes into three tiers:

- **Direct edit:** comments, docs, a few lines of data. Do it yourself, no review.
- **Light:** a single-point fix in one file with no behaviour change. Hand it to a subagent, review the diff once.
- **Full:** anything that crosses systems, or changes a save format or a public interface. Eight steps: plan → review the plan → trial read → dispatch → write code → hand back → review the code → merge.

The interesting step in the full tier is the trial read. Once a plan is written, a cheap model reads it and lists only the questions it would still have to ask. Any question means the plan hasn't made all its decisions yet. Fill the gap and read again, and dispatch only when no questions remain. The agent writing code then gets a brief it can follow without making choices of its own.

If an agent finds mid-task that the plan doesn't match reality, it stops and hands back, naming the premise that failed. The fix goes into the plan, not into a workaround in the code.

**The commit gate** is the hard core of this part. `/nomess:init` installs two native git hooks, `pre-commit` and `pre-merge-commit`. Native git hooks rather than Claude Code tool hooks, because git doesn't care who is committing: an AI, a human in a terminal and an IDE button all go through the same check.

The hook checks the tree that is about to be committed, not your working directory. It takes the staged tree from `git write-tree` and reads the config and baseline and runs the detectors on that tree. Unstaged drafts don't affect the result, and with `git add -p` only the staged half is checked. On the main branch, generated files such as the system map are refreshed inside the same commit: nomess layers the refreshed content onto the candidate tree, checks it all together, and once everything passes writes those exact checked bytes into the index. What was checked is always what gets committed.

In a hurry, `git commit --no-verify` skips the hook. An AI that tries the same trick is stopped by a Claude Code hook that splits the command by shell rules and recognises `--no-verify`, `-n` and attempts to change `core.hooksPath`.

### ③ The system map and self-updating docs

nomess generates a system map from the source code in `docs/system-map/`: which subsystems exist, who depends on whom, and which files are depended on most. Python imports are read from the syntax tree, so an `import` inside a string or comment isn't counted. Other languages are scanned with regular expressions.

Design documents can contain generated sections, fenced by two marker lines, whose contents come from a script. Every commit on the main branch refreshes them, so docs and code stay in step within the same commit. Broken links and stale generated sections show up in the checks.

The system map is a map of what exists today, meant for the AI: before planning a change, it shows which subsystems the change will touch. People read design documents such as `docs/overview.md`, which explain intent and reasoning. nomess doesn't write those for you, but it points out where they no longer match the code.

### ④ Memory and lessons

Lessons learned the hard way are recorded with `/nomess:lesson` and land in `docs/lessons/inbox.md`. Each has a title, a one-line summary and a body, and can be tagged with the paths it applies to.

Every so often, `/nomess:dream` tidies the inbox and memory: it merges duplicates, drops what's outdated, and turns verified lessons into rules. It proposes first. Once you confirm, it does everything in one go and commits, and `git revert` undoes it if you don't like the result. A run costs about 95,000 tokens, so it only runs when you ask.

Why not a vector store or a knowledge graph? The data doesn't call for one. A project has tens to a few hundred lessons and memories; organised by directory with an index, they're easy to find. Vector search would add a dependency, storage you can't read, and no clear answer to "why did it find this one?" Markdown files open in any editor, live in git, and show up in code review.

### ⑤ Path-scoped rules

Verified lessons become `.claude/rules/nomess/*.md` files, each starting with the paths it applies to. Claude Code loads a rule only when the AI reads a file under a matching path, so rules don't sit in context or cost tokens the rest of the time.

The effect: when the AI opens a file under `src/save/`, it sees "saves go through save.py only" or "a save-format change needs a migration" — rules the project paid for with past mistakes — without anyone copying them into every brief.

### ⑥ Mess detection

These are the built-in detectors that run inside the commit gate, about a dozen of them, all scripts, no AI.

**Copy-paste (D1).** Code is split into tokens with whitespace and comments removed. Every run of 25 tokens is hashed, and the winnowing algorithm picks representative fingerprints. This is the classic plagiarism-detection method, and it guarantees that any duplicate of 50 tokens or more is found. When two files share a run of fingerprints, the match is extended in both directions to find the full duplicated range. Exact copies are red; copies with renamed variables are yellow, because fingerprints are computed after identifiers are replaced with placeholders, which also catches renamed clones. A snippet that appears in more than ten files is treated as boilerplate and no longer reported.

**One entry point per job (D4).** The config states "this is done only here", for example "saves go only through `save.py`". The same pattern in any other file is reported.

**Between subsystems (A1–A4 and relations).** The config says which paths belong to which subsystem, so every edge in the dependency graph becomes "this subsystem uses that one". The checks: subsystems forming a cycle, a lower layer depending on a higher one, a dependency between two subsystems declared independent, an explicitly forbidden dependency, and data written by more than one subsystem.

**Parallel packages touching the same files (C4).** In a large project, each package in the schedule lists the files it may change. If an existing file matches two packages that are both in progress, it's red. Overlaps inferred only from a shared path prefix are yellow.

**Smells.** Swallowed exceptions (P1) are judged from the syntax tree by what the `except` block actually does: only `pass`, or catching everything and logging a line, counts as swallowing; cleaning up and re-raising does not. Hack comments (P2), names like `_v2` or `_old` (P5, usually a sign of old and new versions living side by side), and overlong files and functions (S1, S2) are simple matching and counting.

**Docs.** Duplicated content across documents (PL-DUP) is found with the same fingerprints as copy-paste. A plan that mentions paths or systems that no longer exist (PL-STALE) is flagged as possibly stale.

**The ratchet: things only get better.** At install time every existing problem is recorded in the baseline `.nomess-baseline.json`: which rule, which file, how many. From then on each commit is compared against it. New problems are blocked. Worsening problems are blocked too, such as one more occurrence in the same file or a file that grew longer. Anything already in the baseline passes. Fixed problems are removed from the baseline at the end of a batch and can't come back.

A ratchet is only useful if nobody can quietly loosen it, so there are two guards. B1 protects the baseline: a commit that adds entries or raises counts is caught. B2 protects the config: turning a check off, raising a threshold, deleting a rule or changing a subsystem's paths all count as loosening. Either kind of change needs a human to put the `nomess-loosen` label on the PR before CI lets it through.

Results are cached by file content hash, so unchanged files aren't re-analysed, and a commit only checks the files it touches. False positives are kept down by severity: only the most certain cases are red and block by default; anything that might be a misjudgement is yellow. For a genuine exception, add an `allow` entry with a reason to the config, and review always looks at newly added exceptions.

## Fitting projects of different sizes

Flexibility comes in four layers, from coarse to fine:

1. **Three sizes.** `size` in `nomess.json` is `small`, `medium` or `large`. It sets which detectors are on by default, which review level applies and which files init creates. Small projects get copy-paste, swallowed exceptions and overlong files, the lightest review, and only the system map's front page. Medium adds subsystem cycle detection and the paged system map. Large adds parallel-package overlap, doc duplication and stale plans, plus a master schedule and an ownership map. Size only sets defaults; anything you set explicitly wins.
2. **Per-directory strictness.** `scopes` give different settings to different directories: strict in the core, relaxed in tools, no length limits in tests. When a file matches several scopes, the most specific path wins.
3. **Individual switches and thresholds.** Every detector can be turned on or off, recoloured and tuned on its own.
4. **Suggested size changes.** nomess looks at recent commit history. Several branches merging in parallel suggests moving up; a long stretch with one person working suggests moving down. The suggestion appears in `nomess status` and the VS Code status bar, and a person decides.

## Design choices

**Why native git hooks.** An early version intercepted commit commands with Claude Code tool hooks. That only covered the AI, missed humans committing from a terminal, and meant guessing every shell spelling. Git calls its own hooks on every commit, whoever makes it and however it's made. nomess coexists with husky and the pre-commit framework: it never overwrites someone else's hook and prints a one-line recipe to wire itself in instead.

**Why check the index rather than the working directory.** The index is what gets committed. Check the working directory and you could fix something without staging it, pass the check, and commit the unfixed version.

**Why only block new problems.** Demanding that all existing problems be fixed first usually means nobody installs the tool. The ratchet leaves old debt where it is, guarantees things don't get worse, and tightens over time.

**Why the text is short.** The only things always in context are the descriptions of two skills and two subagents, plus the nomess section of `AGENTS.md` (at most 12 lines): about 530 tokens. Everything else loads on demand. The workflow loads when planning, and a directory's rules load when its files are opened.

**It isn't a security boundary.** Anyone determined to get around it can type `--no-verify`. nomess guards against not noticing, not against doing it on purpose. To actually hold the line, run `nomess check --ci` in CI. It reads the config and baseline of both commits directly, depends on nothing local, and requires the PR label for any loosening.
