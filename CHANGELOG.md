# Changelog

Versions follow [Semantic Versioning](https://semver.org/). Each release has three parts: Added, Changed, Fixed; breaking changes come first, with migration steps.

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
