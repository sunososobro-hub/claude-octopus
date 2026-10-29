---
description: "Wake up: read a checkpoint and continue; <keyword> searches checkpoints + memory; --memory browses the memory index"
---

# oct-wake

Resume from an `/oct-nap` checkpoint; also the entry to long-term memory.

Args: none = latest unconsumed; `<hash>` (8 chars); `--list`; `--list all` (active + archived); `--memory`; `<keyword>` (checkpoints + memory).

Setup (prefix every Bash call; `SUM` = checkpoint dir, also used in prose):

```bash
SUM="${CLAUDE_CONFIG_DIR:-~/.claude}/summaries"
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
```

Pools: checkpoints (`$SUM/`) and long-term memory (`${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/memory/`; `<slug>` = cwd with every `/` replaced by `-`; the dir named in the system prompt's auto-memory section). `MEMORY.md` there is the index: read only it to list/search; read memory files only after the user picks them.

## Step 0 — Entry-fee check

In the same Bash call as Step 1's reads run `$PY "$SCRIPT" --entry-fee-check 2>&1`. No output is normal: say nothing. If it prints a line, show it as-is and ask its accept/decline question; yes -> `$PY "$SCRIPT" --entry-fee-accept` and confirm briefly; no/no response -> leave baseline alone. Inline; do not delay Step 1.

## Step 1 — Find it

`$SUM/index.md` has one line per active checkpoint (hash, date, project tag, task one-liner); `/oct-nap` maintains it and archives older same-project checkpoints. Use `index.md` for all listing, clustering and keyword search; open a checkpoint file only in Step 2.

One Bash call with Step 0: `$PY "$SCRIPT" --wake-state 2>&1` prints the index, the checkpoint files (`*.md` except `index.md`; `(none)` when empty) and `.last_woken`. Never make a separate Bash call just to read `.last_woken`. Reconcile:
- File with no index line: read only its task line, append a line to `index.md` (create with header if missing).
- Index line with no file: drop it only if the files list has no `<hash>.md` for it; `(none)` means no files at all, not a reason to drop lines that still have files.
- Filenames match index hashes 1:1: render from the index; do not reopen files or re-derive tags.

Sort by index date, newest first. When reading a checkpoint file, read `## Task` / `## Next Steps`.

- `--list`: 5 most recent active (hash, date, task line); if more, add `...N more older ones, use --list all to see everything`. STOP; load nothing.
- `--list all`: sections In progress (all active) and Archived (`$SUM/archive/*.md` if present). STOP; load nothing.
- `--memory`: read `MEMORY.md` only; numbered list (name + description); ask which to load. STOP until the user picks.
- Hash: use that file (active or archived).
- Other non-flag argument (keyword, project, phrase): search active + archived checkpoints (task line + content) and `MEMORY.md` index lines. One numbered list, each hit tagged by source:

  ```
  🔍 Related to "<keyword>"

    1  Checkpoint  <hash>  <date>  <task line>
    2  Note  <memory name> — <description>

  Load which? (e.g. "1", "2 3")
  ```

  Always confirm, even with one hit. Exception: if the user's phrasing already says exactly what they want ("load the memory for X") and one clearly-most-relevant candidate remains after ruling out false positives by content, load it and report what was loaded. Ask only if 2+ indistinguishable candidates remain.
- No args: count active checkpoints, cluster by project (Grouping rules).
  - One checkpoint total: load it.
  - One cluster: list it (numbered, hash, date, task line); ask which.
  - Several clusters: show only cluster names (count + latest date):

    ```
    You have N projects in progress:

      1  <project>   3 checkpoints, latest <date time>
      2  <project>   1 checkpoint, latest <date time>

    Which project do you want to resume?
    ```

    After the pick: one checkpoint -> load it. Several are successive snapshots of one task: read all, synthesize one todo view, ask yes/no (not a numbered pick):

    ```
    📋 <project> — N checkpoints merged (latest <hash>, <date time>)

    Current status: [latest checkpoint's ## Task, one line]

    ✅ N items done (type "expand" to view)
    ❓ N items look done (unmarked, worth confirming first)

    Todo
    - [ ] [still-open items, oldest-written first]

    [latest checkpoint's ## Decisions / Watch, in full]

    Resume?
    ```

    - Walk oldest to newest. Open items = union across the cluster; an item leaves only when ticked `[x]` or `[-] dropped: <reason>` in a later checkpoint. Dedupe by item, keep latest status.
    - Show only open `[ ]`. Collapse `[x]`/`[-]` into the `✅ N items done` line; expand to a `- [x]` list only on request ("expand").
    - An item that only sounds finished (later Task/Key Findings) but was never ticked goes on the `❓` line; never in the done count, never silently dropped.
    - Current status = latest Task line. Decisions = latest `## Decisions / Watch` in full (never collapsed, not merged across checkpoints).
    - Unrelated sub-threads rather than a linear progression: say so and list them numbered.
    - "Resume?" yes: use the cluster's latest checkpoint for Steps 2-3. Mention once that older ones look superseded (next `/oct-nap` on this project archives them); do not archive yourself.
  - The drill-down applies only to the no-arg call, regardless of `.last_woken`; never default to "most recent". `.last_woken` only drives the SessionStart nudge.

After `/clear`, the SessionStart hook `auto-wake.py` injects the latest checkpoint and `.last_woken`: confirm in the Step 4 format and skip Steps 1-3 except 3b (use the injected nap_verify output).

No checkpoint files: say so, suggest `/oct-nap` before clearing; fabricate nothing.

### Grouping rules

- Group by the `index.md` project-tag column (set at nap time from `## Task`). Re-derive a tag only for a checkpoint just added in reconciliation (ticket ID, repo/app, or initiative in its task line).
- Identify the project from the task line only; do not scan bodies or chain checkpoints via passing mentions. A task line spanning projects clusters by that combined identity.
- Clusters newest first; within a cluster newest first, numbered from 1 per cluster. A checkpoint with no shared project gets its own cluster. Archived stays flat.
- Numbers repeat across clusters: accept a hash or "cluster name + number".

```
📋 Checkpoints in progress

<project A>
  1  <hash>  <date time>  <task line>
  2  <hash>  <date time>  <task line>

<project B>
  1  <hash>  <date time>  <task line>
```

### Due dates

No `## Due`: ordering above. With it:
- Badge after the task line: `📅 YYYY-MM-DD` for a date; the phrase as written with `⏰` when not a date (`⏰ this is urgent`); `⚠️ YYYY-MM-DD` instead of `📅` if past.
- Within a cluster: due first, soonest first; non-dated urgency phrases above dated ones.
- A cluster with any due checkpoint sorts ahead of clusters without one.

## Step 2 — Load it

Checkpoint: read the file (~1-2k tokens); do not read the session transcript or reconstruct more than it holds. Combine with Step 3 in one Bash call (also when reading several for cluster synthesis); not when only memory files are read.

If `## Related Memory Files` lists memory files, do not auto-load: list them (name + one-line description from `MEMORY.md`) and ask which to pull in.

Memory file: read the selected `.md` files; do not echo content. Confirm only: `✅ Loaded: <name>, <name>`

## Step 3 — Mark consumed (checkpoints only)

```bash
cat $SUM/<hash>.md; echo "<hash>" > $SUM/.last_woken
```

Skip if only memory files were loaded.

## Step 3b — Quotes and in-flight check

If the checkpoint ends with `## User quotes index`, compare its quotes and numbered proposals with Next Steps; show each unmatched ask as `⚠️ In the quotes but not in the todo list: ...` (one line each) and add it to Next Steps.

If it has `## Running agents`, `## Pending dispatch` or a `Collect <name>` item: use the nap_verify section injected by auto-wake, or run `$PY "$(dirname "$SCRIPT")/nap_verify.py" $SUM/<hash>.md` (same Bash call as Setup):
- `✅` -> tick its `Collect <name>` item `[x]`; an `(inferred)` check only means the agent stopped: read its result first.
- `⏳` -> still running; wait for its completion notice, do not re-dispatch.
- `❌` -> add the printed `- [ ] Chase ...` line to the todo and handle it this turn.
- `Pending dispatch` -> the user already asked: dispatch in this reply without asking.

## Step 4 — Confirm

```
✅ Woke from <hash> (<date time>)
Task: [one-line summary from ## Task]
[## Awaiting Reply items, if present, first, as written]
[📅/⚠️ Due line, only if ## Due exists]

✅ N items done (type "expand" to view)

Next steps:
- [ ] [each still-open item from ## Next Steps, as written]

[## Decisions / Watch, if present, in full]
```

- Show only open `[ ]`; fold `[x]`/`[-] dropped` into the done line (omit it if nothing is checked); expand only on request.
- `## Decisions / Watch` is always printed in full, never collapsed.
- Do not reprint other checkpoint content.
