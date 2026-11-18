# Changelog

Versions follow [Semantic Versioning](https://semver.org/). Each release has three parts: Added, Changed, Fixed; breaking changes come first, with migration steps.

## 0.9.0 – unreleased

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
