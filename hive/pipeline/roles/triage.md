# Role: triage

Read this before triaging, writing or opening an issue.

Moved verbatim from AGENTS.md (sections 9, 10). `<dev-branch>`, `<main-branch>`, `<test-command>`, `<protected-paths>`, `<keeper>`, `<areas>` are the values filled in at the top of AGENTS.md.

## 9. Issue format
- English. Body lines: `Why:` `Goal:` `Acceptance:` (measurable: a number, behaviour or command output) `Verify:` (the command or steps). Optional `Out of scope:`. Child issues link `Parent: #N`.
- Labels: exactly one `area:*`, one type (`bug`, `enhancement`, `eval`, `documentation`, `maint`), one priority `P0`..`P3`, one `model:*`.
- An `enhancement` or infrastructure issue names the real user it helps; without that it is P3.
- Work that only maintainers or agents ever see (dashboards, tooling for the pipeline itself) is `infra` and limited to about 10% of effort. Build the product, not the machine.

## 10. Opening new issues
- Open new issues only with evidence: a failing test, a crash log, a user report, a measured gap, or docs missing for a merged change.
- Features come only from keeper-approved proposals. Ideas go in as `status:proposal`, at most 2 per day, only while fewer than 3 are open.
- If the test job on the fast lane tip stays red for more than 2 hours, open a `[P0] dev red` issue; everyone takes it before anything else.
