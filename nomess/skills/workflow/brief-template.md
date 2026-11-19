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
Fix root causes, don't patch; no defensive code; one entry point per job; list changes outside the brief separately. If you change ownership or an interface, put the owner-record change (large: the ownership map, `<docs_root>/ownership-map.md` by default; otherwise `## How to use` of the system page) in the handback instead of editing shared docs; update comments and docs in your own files in the same commit. Work in your own worktree, add only your own files (no `commit -a`), commit locally only, no push. Blocked by the commit check: fix it, or add an `allow` with a reason and say so in the handback.
Tests: only for edge behavior hard to deduce from the code and easy to regress; what reading the code confirms goes into the handback as "confirmed by reading code: file:line". One test checks one thing; no timing assertions; run only the tests your change touches; don't run the full suite (it runs once after the batch is merged).
Before the last commit, record what code and git don't show with `nomess.py lessons add "<title>" -s "<when>" -b "<what>" -k "<aliases>" --unverified` (learned from outside the repo: also `--external "<source>"`), so it goes into that commit.

## 7. Handback checklist
Three things: the commit; the verification result (check result in one line; tests added and the acceptance item each covers; items confirmed by reading code, with file:line); where it deviated from the plan (failed premise and what you saw, changes outside the brief; "none" if none). Add `Looked up: <link>` only if what you found changed a decision.

Acceptance criteria:
- Tests: ... (edge behaviors that become test cases)
- Confirmed by reading code: ... (the executor gives file:line in the handback)
