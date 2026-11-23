# Role: merge

Read this before merging or reviewing a PR.

Moved verbatim from AGENTS.md (sections 5, 6). `<dev-branch>`, `<main-branch>`, `<test-command>`, `<protected-paths>`, `<keeper>`, `<areas>` are the values filled in at the top of AGENTS.md.

## 5. Merge gates (two lanes)
- `<dev-branch>` is the fast lane: the only CI gate is the test job. Other failing checks never block a merge; open one issue `[dev] <check> failing on dev` instead of waiting.
- `<main-branch>` is the quality lane: all checks, reached only through the release process.
- A PR is ready when: base is `<dev-branch>`, not draft, no conflicts, test job green on the head commit (no check at all is not green), the body links an issue, the diff meets the issue's single `Acceptance:` line (the merger checks it and says so in one line, otherwise `AI review: FAIL - acceptance`), and the last line of the body records the minutes spent.
- Check CI once. Not finished = skip that PR this run; never sleep or poll inside a session. Workers do not wait for CI after opening the PR.
- A PR touching `<protected-paths>` needs an explicit `Strong review: PASS` comment from the reviewer identity, newer than the head commit. The reviewer names the full head SHA on that line. A PASS on an older head still counts only while that SHA is an ancestor of the PR head, no protected path changed between the two, and no FAIL, CHANGES, `needs keeper` or `blocking` comment is newer than it. Authors never approve their own PR. Use a distinct reviewer account or bot when you can; in a single-account setup, where every agent posts as `<keeper>`, a PASS counts only from a run that did not open the PR, and that rests on trust.
- Reviewer FAIL only for: contradicting a keeper comment, tests that merely read or grep source, thresholds changed without data, unrelated changes, secrets, new network calls. Post the reason, return the issue to `status:todo`, leave the PR open.
- Paperwork gaps (missing link, usage line misplaced) are fixed by the merger, not failed.
- Hard stops: unresolved `blocking` review text; the issue is `status:frozen`, `status:proposal` or `needs-keeper`.
- Diff size alone never escalates a review. Adding a skip marker or deleting a test is flagged in review text, not auto-blocked on the fast lane.

## 6. Conflicts
- A PR with conflicts: merge `<dev-branch>` into its branch, resolve keeping both sides' intent, rerun `<test-command>`, push.
- Close and redo only if the resolution would touch more than about 50 lines or change another PR's behaviour.
