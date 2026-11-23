# Role: ops

Read this for model choice, throughput caps and throttle.

Moved verbatim from AGENTS.md (sections 7, 8). `<dev-branch>`, `<main-branch>`, `<test-command>`, `<protected-paths>`, `<keeper>`, `<areas>` are the values filled in at the top of AGENTS.md.

## 7. Model choice
- Use the strongest model only for hard domains (concurrency, hardware-dependent code, quality evaluations). Everything else the light model, whatever the size.
- If a light-model attempt fails once (PR closed, or CI red twice), relabel `model:strong` and retry on `fix/N-r2`.

## 8. Throughput caps
- At most 10 issues in `status:doing` across all agents.
- Light-model workers take up to 4 items per wake; strong-model workers up to 2.
- Mergers merge every ready PR in one run. Reviewers handle up to 4 strong-review items per run, oldest first.
- Optional throttle: one pinned issue whose first line is `level: N` (0 off, 1 only P0/P1, 2 normal, 3 high, 4 max: as 3, plus the supervisor works items). Unreadable means 2. Line 2 may be `focus: <labels>`, line 3 `mix: <type> <n>, ...` (effort targets the keeper edits there). Merging green PRs continues at every level.
