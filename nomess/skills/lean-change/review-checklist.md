# Review checklist

Review looks only at the review input (the output of the `review-input` command: review level, must-review items, new red and yellow findings, related lessons, diff) and the design excerpt. Red and yellow findings the script already reported are not re-checked by hand; every new `allow` in the must-review section must be looked at: is the reason true, could the code be fixed instead. Go through each:

1. Bugs: edge cases, error handling, concurrency, data loss.
2. Over-engineering: abstractions with one implementation; options and switches nobody calls; "just in case" checks and fallback paths; dependencies added for a few lines; hand-written code where the standard library would do; reinventing a tool the repo already has; too many tests, the same behavior covered twice, tests of implementation details.
3. Patches: clamps, special cases or switches hiding a symptom while the root cause is untouched.
4. Duplication and scatter: two entry points for one job; near-duplicate code that should be merged; one function doing several unrelated things (split by responsibility, not by line count).
5. Coupling: reading or writing another module's internal data or private functions directly; binding two modules together for the sake of one caller; a dependency direction opposite to `arch.layers`. Give file:line; fix by going through the other module's public entry point.
6. Out of scope: files outside the scope changed; data owned by another system read or written without updating its owner record.
7. Wrongful deletion: trust-boundary validation, data-loss error handling or security removed.

Every finding must give file:line and a concrete example; re-read the line to confirm before reporting. Give the smallest fix, prefer deleting, don't add layers. A `shortcut:` comment that states its limit is a deliberate decision; don't report it. List anything mechanically checkable separately as "suggest making this a check rule".

Source: the categories and "concrete example + re-read to confirm" are borrowed from ponytail's /ponytail-review (MIT).
