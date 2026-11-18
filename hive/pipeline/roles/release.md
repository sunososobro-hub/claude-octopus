# Role: release

Read this before bumping a version or cutting a release.

Moved verbatim from AGENTS.md (sections 11). `<dev-branch>`, `<main-branch>`, `<test-command>`, `<protected-paths>`, `<keeper>`, `<areas>` are the values filled in at the top of AGENTS.md.

## 11. Releases (optional)
- Only one role bumps the version, patch bumps only, one PR with the gate results in the body. Minor and major bumps are keeper-only.
- Releases are cut from a snapshot branch of the fast lane; later merges never move it. No human clicks merge on the release PR: required checks decide.
- An urgent fix may ship through a separate hotfix path, only for P0 or P1 bugs already merged on `<dev-branch>`.
