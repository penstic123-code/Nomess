# Changelog

Versions follow [Semantic Versioning](https://semver.org/). Each release has three parts: Added, Changed, Fixed; breaking changes come first, with migration steps.

## 1.1.1 – 2026-11-19

### Changed

- When the docs index at the end of the overview is still too long after collapsing archived plans, each document type with several pages becomes one line linking to a generated index page in that type's folder (`plans/README.md`, `systems/README.md`, …). A hand-written `README.md` there (no `type-index` marker) is left alone and that type is not collapsed.
- The tidy's one-sentence summary now names the deleted pages and the most-shortened pages (up to 3 each) and ends with `git show --stat <commit>` to see what changed.

### Fixed

- The automatic tidy could quietly drop a lot of text. If one run deletes more than 60 lines net across project docs and the memory folder (archiving, renames and generated files don't count), the project side is discarded, the memory commit is reverted, and a numbered item in `.nomess/dream-notes.md` lets you run it with `/nomess:dream apply N`. The next run is told not to delete net.
- The tidy no longer fails on a memory folder that has no commits yet.
- The generated plans index page is no longer checked as a plan (PL-STALE).

## 1.1.0 – 2026-11-19

### Breaking changes

- A new `.md` under the doc root (`docs/` by default) that is not in any document-type location is red DOC4 and blocks the commit (the AI is also stopped when it tries to write one); pages already there are only yellow.
- The nomess section of `AGENTS.md` changed: the inbox reminder line is gone; two lines say where docs go and that docs describe things as they are now. The section is refreshed on the next main-branch commit, or by `nomess refresh`.
- `/nomess:dream` no longer writes a proposal and waits: it tidies in a temporary worktree and lands one commit by itself. `/nomess:dream execute [strike N…]` is gone; items that need a person go to `.nomess/dream-notes.md` and run with `/nomess:dream apply N…`.
- `/nomess:init` asks nothing; it runs `nomess init --auto`.

Migration for an existing project, once after upgrading: run `nomess init --auto` (it only fills in what is missing: the `docs-index` and `lessons-index` entries and markers), then `nomess check --freeze` (new yellow findings such as DOC4–7 in existing docs go into the baseline). The automatic tidy stays **off** in projects created before 1.1; turn it on with `"dream": {"auto": true}` in `nomess.json`. A docs site whose source is in `docs/` (MkDocs, Sphinx, Docusaurus, VitePress, mdBook, Jekyll) is detected at run time: its pages count as public docs and are never changed or flagged.

### Added

- Automatic enabling: a SessionStart hook tells the AI, in a Git repo without `nomess.json`, to run `nomess init --auto` before its first file change and tell you in one sentence. No questions (size `small`, language from the conversation, main branch worked out). `nomess off` switches a repo off; `userConfig.auto_init` switches it off everywhere.
- Automatic tidy: when the inbox, unverified entries, misplaced or over-long docs, merged schedule rows or stray `.md` files pass a threshold (at most once a day, and only if something changed), the hook asks the AI to run `nomess:dream` in the background. `nomess dream begin | land | abort | git-log` does the mechanical part: lock, temporary worktree, guard rails, commit, cherry-pick onto the current branch, a one-sentence summary with the undo command. A failed landing is discarded, never retried. Config `dream: {auto, stale_days, max_items}`.
- No permission prompts: the PreToolUse hook allows the plugin's own whitelisted commands and edits inside the tidy worktree and the project memory folder.
- Document types are enforced: DOC4 (misplaced), DOC5 (orphan pages), DOC6 (over the length budget, `doc_budget`), DOC7 (system page possibly out of date); `doc_types` registers extra types; a generated `docs-index` lists every doc at the end of the overview.
- Three tiers of docs: project docs (`docs_root`, default `docs`) are fully managed; developer docs (`dev_docs`, by default `CONTRIBUTING*` and the like) are only edited in place; public docs (`public_docs`, by default `README*`, `CHANGELOG*` and the like, plus a detected docs-site source) are never changed automatically. When the docs site lives in `docs/`, `init --auto` puts project docs in `project-docs/`.
- Lessons carry aliases (`lessons add -k "存档, save, persistence"`), matched like titles. A lookup by file also scores the entry's `Paths:`, the same module and modules it directly depends on, with the reason marked.
- `lessons add --external <source>` records where a lesson came from and keeps it unverified; such entries never become rules and the tidy cannot verify them (L6 in review input when someone does).
- Lessons titled `Doc gap:` / `文档缺口:` are gathered by the tidy into a proposal.
- Templates: `AGENTS.md` gets an "Environment and running" heading; the system page has four fixed sections (What this is, How to use, Pitfalls, Known issues).

### Changed

- DOC1 also checks developer and public docs (README and the like), yellow only.
- `lessons_remind` is now the inbox threshold for the automatic tidy.
- The `workflow` skill: a `small` project runs `nomess init --auto --size medium` before its first parallel dispatch; doc paths follow `docs_root`.

## 1.0.0 – 2026-11-18

### Removed

- Automatic level up/down suggestions (`suggest.py`, `status --suggest`, the `suggest` config section).
- The `py` generator in `docgen` (only `map`, `cmd` and `builtin` remain).
- `level` and `review` keys in `scopes`; old configs that still use them get a yellow CFG1.
- Pre-built `docs/overview.md`, `docs/systems/*.md` and the lessons library from `init`; a missing system description page is no longer reported (DOC3 still checks the head of pages that exist).

### Changed

- `init` lays down only the required files; the rest are created when first used.
- Decision ladder squeezed from seven levels to three questions; handoff reduced to three items.
- Workflow has five tiers (direct edit / light / medium / full / system), each adding one thing to the previous. Light is not reviewed alone (except under `strict`); medium gets one code review; system = building or redoing a whole system, adding a design doc, prototype check, user sign-off and milestones; full backs up or dry-runs irreversible operations first; briefs and trial reads are used only when work is handed to another agent.
- README rewritten with memory at the center and six concept diagrams.
- `review.cmd` is now run with `nomess review-input --cmd <base> [excerpt]`.
- Loop limits: plan review and trial read at most two rounds (then ask the user); code reviewed once, fixes re-reviewed only if they change the design or add files; a second rework of the same package stops for the user.
- The `AGENTS.md` entry mentions `docs/overview.md` only when it exists.

## 0.9.2 – 2026-11-18

### Added

- README in bullet notes with 16 hand-drawn concept diagrams (rough.js; English and Simplified Chinese); hand-drawn quokka logo.

### Changed

- Faster commit check: file header facts are cached and shared by the system map and the header check; subsystem ownership matches each file only against globs with the same top directory; one `git check-attr` call per commit; `git diff --quiet` runs only when a `cmd` rule needs it.

## 0.9.1 – 2026-11-18

### Added

- Review level `off` turns review off entirely, globally.
- Rules in the project's `AGENTS.md` or `CLAUDE.md` take precedence over the `workflow` and `lean-change` skills.
- README rewritten: each of the six parts explained with an example, how it works and why it is built that way (English and Simplified Chinese).
- Logo.

### Changed

- Faster commit check on large repos: compact fingerprint cache, one `git ls-files` per check, unchanged files read their object name from the index, batched `cat-file`, fewer copy-paste seeds to extend. On a 5,000-file repo, a commit touching 30 files goes from about 7.4 s to 5.7 s.
- Copy-paste detection decides per file whether `smells.extra_ext` applies; doc-duplicate detection reuses the generated-section parser.

### Fixed

- Tests and CI on Linux, macOS and Windows: executable bit on test hook scripts, Windows short paths resolved before deriving the Claude project folder, Python 3.9 runs on Ubuntu 22.04.

## 0.9.0 – 2026-11-18

First public release.

### Added

- Skills: `lean-change` and `workflow` (loaded automatically); `/nomess:init`, `/nomess:review`, `/nomess:lesson`, `/nomess:dream` (manual).
- Subagents: `reviewer` and `trial-reader`, both read-only by instruction (their tool list includes the shell).
- Commit gate: `pre-commit` and `pre-merge-commit` git hooks (`nomess hooks install | uninstall | status`; husky and the pre-commit framework get a recipe instead of being overwritten). A `PreToolUse` guard refuses an agent's `--no-verify` and `core.hooksPath` changes. Generated files are refreshed inside the same commit on the main branch. Scripts only, no model calls.
- Baseline and ratchet: `nomess check --freeze | --tighten`, loosening detection, and `nomess check --ci --base <SHA> [--allow-loosen]` for CI (PR label `nomess-loosen`).
- Built-in checks by project `size` (`small` / `medium` / `large`), per-directory `scopes`, a single `allow` list with reasons, and subsystem constraints (`arch`).
- `nomess` script: `check`, `docgen`, `map`, `rules`, `lessons`, `status`, `doctor`, `review-input`, `refresh`, `hooks`.
- Path-scoped rule files under `.claude/rules/nomess/`, generated from verified lessons and system-page pitfalls.
- English and Simplified Chinese: init templates, script messages, field names.
- Trigger cases for `claude plugin eval` (`nomess/evals/`).

### Changed

- None (first release).

### Fixed

- None (first release).
