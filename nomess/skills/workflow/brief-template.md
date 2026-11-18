# Brief template (seven sections; don't dispatch with one missing)

## 1. Goal
After the change, what got simpler and which behavior is now correct.

## 2. Check the current state first
Check the file:line refs, function names and behavior below against the current mainline; if they disagree, stop and hand back instead of forcing an outdated brief.

## 3. Established facts
`file:line` + one-sentence conclusion, noting the commit it was read from. Mark unmeasured ones "deduced".

## 4. File scope
- May change: ...
- Being changed in parallel, do not touch: ... (which package)
- Dependencies and merge order: ...

## 5. Out of scope
Nearby work that does not belong to this package.

## 6. Rules (paste verbatim)
Fix root causes, don't patch; no defensive code; one entry point per job; list changes outside the brief separately; if you change ownership or an interface, put the owner-record change (large: `docs/ownership-map.md`; otherwise `## Details` of the system page) in the handback (don't edit shared docs) and update comments and docs in your own files in the same commit; work in your own worktree, add only your own files, commit locally only, never `--no-verify`; blocked by the commit check: fix it, or add an `allow` with a reason and say so in the handback.
Tests: write tests only for edge behavior that is hard to deduce correctly from the code and easy to regress; acceptance items that reading the code can confirm go into the handback as "confirmed by reading code: file:line", with no test; one test checks one thing; no timing assertions; during development run only the tests you changed, the full suite once before handing back. Whether the logic is right is mostly judged by review.
Before the last commit, record what code and git don't show with `nomess.py lessons add "<title>" -s "<when>" -b "<what>" --unverified`, so it goes into that commit.

## 7. Handback checklist
Commit hash; check result in one line; failed premise ("none" if none, else which premise and what you saw); changes outside the brief ("none" if none); premises deduced but not measured; ladder line (`Ladder: …; Looked up: …`, per `nomess:lean-change`); tests (added ones and the acceptance item each covers; items confirmed by reading code, with file:line); lesson (title recorded before the last commit; "none" if none).

Acceptance criteria:
- Tests: ... (edge behaviors that become test cases)
- Confirmed by reading code: ... (the executor gives file:line in the handback)
