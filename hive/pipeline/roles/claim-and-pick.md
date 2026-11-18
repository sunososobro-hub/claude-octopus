# Role: claim and pick

Read this before claiming or picking an issue.

Moved verbatim from AGENTS.md (sections 2, 3, 4). `<dev-branch>`, `<main-branch>`, `<test-command>`, `<protected-paths>`, `<keeper>`, `<areas>` are the values filled in at the top of AGENTS.md.

## 2. Claiming
- Claim an issue by creating its branch from `<dev-branch>`. If the branch already exists, someone else has it: take the next item.
- After claiming, label the issue `status:doing`. When the PR is open, swap to `status:review`.
- Never start an issue that has an open PR linking it or a live branch for it.
- Exception: after a failed review the issue returns to `status:todo` and keeps its PR. Push the fix to the same branch.
- A branch whose last PR was closed unmerged does not hold a claim. Retry on the next `-rK` branch starting from the closed PR's head, and read that PR's review first.
- Orphans: a `status:doing` issue with no open PR and no new commit after about 20 minutes (light model) or 45 (strong model) goes back to `status:todo`.

## 3. Picking work
- Eligible: open, labelled `status:todo` and `ok-to-work`, not `status:proposal`, `status:frozen`, `status:blocked` or `needs-keeper`.
- Never work an issue lacking `ok-to-work`. Issues from outsiders get it only after a trusted person confirms them.
- Order: P0 and P1 first. Then the work type furthest below its target share of effort. Inside a type: focus labels, then P0 to P3, then lowest issue number.
- Never idle while an eligible item exists. When you stop with items left, list up to five as `skipped: #N (reason)`.
- Triage is not work: on a new issue, only add labels (type, priority, model, area) and normalize the body. Work it at once only if P0 or marked urgent.
- Hardware-dependent code that a cloud runner cannot exercise is not a reason to skip: implement, merge on green CI, and post a "how to test" comment for the keeper.

## 4. Area claims and file overlap
- Each issue carries exactly one `area:*` label. Skip an issue whose area already has a `status:doing` issue (P0 exempt).
- The area is free again when the issue moves to `status:review`. Open PRs do not hold an area.
- Race rule: after claiming, if another non-P0 `status:doing` issue in the same area has a lower number, release yours (delete your branch, back to `status:todo`) and take the next.
- Before claiming, list files touched by open PRs. Skip an issue that names the same files (P0 and P1 exempt).
