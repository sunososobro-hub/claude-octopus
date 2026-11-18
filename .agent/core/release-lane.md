# Profile: release-lane (optional)

Active only when project.yml has `release_lane: snapshot`. Default is `none`: then `<main_branch>` is updated by humans or a project-specific process and this file is ignored. Values in `<...>` are project.yml keys.

## Principle
`<dev_branch>` is the fast lane; `<main_branch>` is the quality lane. The keeper never clicks merge on the release PR; gates decide.

## Protected paths (added when enabled)
With `release_lane: snapshot` these are protected (Strong PASS) in addition to `protected_paths`: every release workflow (release, release-pr, auto-release*, hotfix), every workflow listed in `release.required_checks`, `<release.version_file>`'s version line, the release-notes/check scripts, and packaging/installer dirs. The commented block in `hive/pipeline/project.template.yml` lists them; a project must keep them in `protected_paths`.

## Release PR
Mergers and workers never merge, approve, close or edit the release PR (`release/vX.Y.Z -> <main_branch>`); only the auto-release workflow merges it.

## Required checks
- `release.required_checks` (list of workflow names, e.g. ci, e2e, build) must be `success` on the snapshot head. `skipped` does not count.
- Optional deferral: if a check in `release.deferrable_checks` has not started within `release.defer_wait_min` minutes (no runner), it is deferred; release notes say so, and a later failure opens a P0 `[release] deferred <check> failed on vX.Y.Z`. A started run is never deferred.

## Snapshot (no freeze)
- When the test job passes on a dev push and dev's `<release.version_file>` version X.Y.Z has no tag `vX.Y.Z`, the release workflow creates `release/vX.Y.Z` at the bump commit, dispatches the required checks on it and opens the release PR `release/vX.Y.Z -> <main_branch>`, title `release: vX.Y.Z`. Later dev pushes never move the snapshot; the snapshot never gets new commits.
- Red check: re-run for a flake, else fix on dev and let the reviewer open the next patch bump; the old snapshot PR is closed as superseded.
- Only the release workflow creates or deletes `release/v*` branches (the reviewer only when the workflow prints the command).
- Release PR open > 24 h: the supervisor opens P0 `[release] release stuck`.

## Version bumps
- Only the reviewer bumps the version, patch only, one PR `release: bump version to X.Y.Z` with gate evidence. Cadence: tag for current version exists; dev ahead of main by >= 1 merged PR; test green on dev tip; no open bump PR; no hotfix in progress; and >= `release.min_hours_between` h since last release or a P0/P1 bug fix merged since. A different strong-model run gives the PASS. Minor/major bumps are keeper-only (the keeper says so in an issue comment). Any other PR touching the version is a hard stop (`needs-keeper`).

## Kill switch
- Auto-release AND the hotfix workflow run only when repo variable `AUTO_RELEASE` is `true` AND throttle level >= 1.

## Hotfix lane
- Only the reviewer dispatches the hotfix workflow, only for an open or just-closed P0/P1 bug whose fix is merged on dev; never during a release, while a bump PR is open, or while dev's version has no tag yet. The kill switch applies to it too. It branches from the latest tag, cherry-picks, builds/tests once, publishes the same artifacts, tags, and opens a back-merge PR `hotfix/vX.Y.Z -> <dev_branch>` (merge commit, merges on green; the only other PR allowed to touch the version). It may contain only the cherry-picked fix plus the version file; any other file is a hard stop (`needs-strong`). The version change alone needs no PASS; if the fix touches a protected path it does.

## Docs fast lane to main
- Docs-only changes (only `README*.md`, `docs/**/*.md`) may go to `<main_branch>` without a release: merge to dev first, then a merger opens `docs/fastlane-N -> <main_branch>` with the same content, test green, rebase merge, no tag; then merge main back into dev. Skip while a release workflow on main is running. `docs/fastlane-N` is an allowed head next to `fix/N` (rules section 2).

## Optional: hardware-dependent code
- If some checks need real hardware (a self-hosted runner), list that workflow in `release.deferrable_checks` so a missing runner does not stall releases. With `device_nightly: true`, a scheduled workflow dispatches it on dev once a night when the tip has no green or pending run; flaky-check issues close after N consecutive green runs.
