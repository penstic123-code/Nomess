# Changelog

Versions follow [Semantic Versioning](https://semver.org/). Each release has three parts: Added, Changed, Fixed; breaking changes come first, with migration steps.

## 0.9.1 – 2026-11-18

### Added

- Review level `off` turns review off entirely, globally or per directory in `scopes`.
- Rules in the project's `AGENTS.md` or `CLAUDE.md` take precedence over the `workflow` and `lean-change` skills.
- A guide to how each part works and why it is built that way: `docs/how-it-works.md` (English and Simplified Chinese).
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
