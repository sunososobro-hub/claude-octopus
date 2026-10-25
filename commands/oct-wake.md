---
description: "Wake up: read a checkpoint and continue (replaces claude --resume); <keyword> searches checkpoints + long-term memory; --memory browses the memory index"
---

# oct-wake

Resume from an `/oct-nap` checkpoint; also the entry point for long-term memory.

```bash
/oct-wake              # Load the latest unconsumed checkpoint
/oct-wake <hash>       # Load a specific checkpoint by its 8-char hash
/oct-wake --list       # List recent checkpoints without loading one
/oct-wake --list all   # List everything: active + archived
/oct-wake --memory     # List long-term memory index, pick what to load
/oct-wake <keyword>    # Search checkpoints AND long-term memory
```

Pools: checkpoints (`${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/`) and long-term memory (`${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/memory/`, `<slug>` = current working directory with every `/` replaced by `-`; the directory named in the auto-memory section of the system prompt). `MEMORY.md` there is the index. Read only the index to list or search; read individual memory files only after the user picks them.

## Step 0 — Entry-fee check

On every invocation, in the same Bash call as Step 1's reads, run:

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
$PY "$SCRIPT" --entry-fee-check 2>&1
```

No output is the normal case; do not mention it. If it prints a line, show it as-is and ask the accept/decline question it poses. On yes run `$PY "$SCRIPT" --entry-fee-accept` and confirm briefly; on no or no response leave the baseline alone. Do this once, inline, without delaying Step 1.

## Step 1 — Find it

`${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/index.md` has one line per active checkpoint (hash, date, project tag, task one-liner); `/oct-nap` maintains it and archives older same-project checkpoints. For all listing, clustering and keyword search use `index.md`; open an individual checkpoint file only in Step 2 after the user picks it.

Reconcile: `--wake-state` prints the index, the checkpoint files (`*.md` except `index.md`; `(none)` when empty) and `.last_woken`. One Bash call, together with Step 0:

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
$PY "$SCRIPT" --entry-fee-check 2>&1
$PY "$SCRIPT" --wake-state 2>&1
```

Never issue a separate Bash call just to read `.last_woken`.
- File with no index line: read just its task line, append a line to `index.md` (create with header if missing).
- Index line with no file: drop the line only if the `files` section lists no `<hash>.md` for it; `(none)` means no files at all, so never treat it as a reason to drop lines that still have files.
- If filenames match index hashes 1:1, render directly from the index; do not reopen files or re-derive tags.

Sort by index date, newest first. When reading a checkpoint's own file, read `## Task` / `## Next Steps`.

- `--list`: show the 5 most recent active checkpoints (hash, date, task line); if more, add `...N more older ones, use --list all to see everything`. STOP; load nothing.
- `--list all`: two sections, In progress (all active) and Archived (`${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/archive/*.md` if present). STOP; load nothing.
- `--memory`: read `MEMORY.md` only. Show entries as a numbered list (name + description). Ask which to load. STOP until the user picks.
- Specific hash: use that file (active or archived).
- Any other non-flag argument (keyword, project name, phrase): search active checkpoints, archived checkpoints (task line + content) and `MEMORY.md` index lines. Show one numbered list, each hit tagged with its source:

  ```
  🔍 Related to "<keyword>"

    1  Checkpoint  <hash>  <date>  <task line>
    2  Note  <memory name> — <description>

  Load which? (e.g. "1", "2 3")
  ```

  Always confirm, even with one hit. Exception: if the user's phrasing already says exactly what they want (e.g. "load the memory for X") and one clearly-most-relevant candidate remains after ruling out false positives by content, load it directly and report what was loaded. Ask only if 2+ candidates remain indistinguishable.
- No flags: count active checkpoints and cluster by project (grouping rules below).
  - Exactly one checkpoint total: load it directly.
  - One cluster only: list its checkpoints (numbered, hash, date, task line) and ask which to load.
  - More than one cluster: first show only cluster names (count + most recent date each):

    ```
    You have N projects in progress:

      1  <project>   3 checkpoints, latest <date time>
      2  <project>   1 checkpoint, latest <date time>

    Which project do you want to resume?
    ```

    After the user picks a cluster:
    - One checkpoint: load it directly.
    - Several: they are successive snapshots of one task. Read all of them, synthesize one todo view, and ask yes/no (not a numbered pick):

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

      Rules:
      - Walk the cluster oldest to newest. Open items are the union across the cluster; an item leaves the open list only when ticked `[x]` or marked `[-] dropped: <reason>` in a later checkpoint. Dedupe by item, keep each item's latest status.
      - Show only open `[ ]` items. Collapse `[x]` and `[-] dropped` items into the `✅ N items done` line; expand into a `- [x]` list only if the user asks ("expand", "what was completed").
      - An item that merely sounds finished (from later Task/Key Findings) but was never ticked goes on the `❓` line, never into the confirmed count and never silently dropped.
      - "Current status" = latest checkpoint's Task line. Decisions = latest checkpoint's `## Decisions / Watch` in full (never collapsed); do not merge Decisions across checkpoints.
      - If the checkpoints are unrelated sub-threads rather than a linear progression, say so and list them numbered instead.
      - On "Resume?" yes: use the latest checkpoint in the cluster for Steps 2-3. Mention once that the older ones look superseded (the next `/oct-nap` on this project archives them); do not archive yourself.
  - The drill-down applies only to the bare no-flag call (`--list` and `--list all` stay flat/full). It applies regardless of `.last_woken`; never default to "most recent". `.last_woken` only drives the SessionStart nudge.

After `/clear`, a SessionStart hook (`auto-wake.py`) injects the latest checkpoint and `.last_woken` automatically: confirm in the Step 4 format and skip Steps 1-3 except Step 3b (use the injected nap_verify output).

If there are no checkpoint files, say so and suggest `/oct-nap` before clearing; do not fabricate one.

### Grouping rules

- Group by the `index.md` project-tag column (assigned at nap time from the checkpoint's `## Task` line). Re-derive a tag only for a checkpoint just added during reconciliation (ticket ID, repo/app name, or initiative name in its task line).
- Identify the project from the task line only; do not scan the body for shared identifiers or chain checkpoints through passing mentions. A task line spanning several projects clusters by that combined identity on its own.
- Clusters sorted by most recent checkpoint (newest first); within a cluster newest first, numbered from 1 per cluster. A checkpoint sharing no project gets its own cluster. Archived section in `--list all` stays flat.
- Because numbers repeat across clusters, accept a hash or "cluster name + number" as the pick.

```
📋 Checkpoints in progress

<project A>
  1  <hash>  <date time>  <task line>
  2  <hash>  <date time>  <task line>

<project B>
  1  <hash>  <date time>  <task line>
```

### Due dates

Checkpoints without `## Due` keep the ordering above. For ones with it:
- Badge after the task line: `📅 YYYY-MM-DD` for a date, the phrase as written with `⏰` (e.g. `⏰ this is urgent`) when not a date; `⚠️ YYYY-MM-DD` instead of `📅` if the date is past.
- Within a cluster, due checkpoints go first, soonest-due first; non-dated urgency phrases above dated ones.
- A cluster containing any due checkpoint sorts ahead of clusters without one.

## Step 2 — Load it

Checkpoint: read the file (~1-2k tokens). Do not read the original session transcript or reconstruct more than the checkpoint holds. Combine with Step 3 in one Bash call when loading a specific checkpoint (or the several read for cluster synthesis); skip the combination when only `MEMORY.md` files are read.

If `## Related Memory Files` lists memory files, do not auto-load them: list them (name + one-line description from `MEMORY.md`) and ask which to pull in.

Memory file: read the selected `.md` files. Do not print their content back. Confirm only: `✅ Loaded: <name>, <name>`

## Step 3 — Mark consumed (checkpoints only)

Write the loaded checkpoint's hash (plain text) to `${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/.last_woken`:

```bash
cat ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/<hash>.md; echo "<hash>" > ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/.last_woken
```

Skip if only memory files were loaded.

## Step 3b — Quotes and in-flight check

If the checkpoint ends with `## User quotes index`, compare its quotes and numbered proposals against Next Steps; show any ask with no matching item as `⚠️ In the quotes but not in the todo list: ...` (one line each) and add it to Next Steps.

If the checkpoint has `## Running agents`, `## Pending dispatch` or a `Collect <name>` item, use the nap_verify section injected by auto-wake, or run `$PY "$(dirname "$SCRIPT")/nap_verify.py" ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/<hash>.md` (`SCRIPT` and `PY` set as in Step 0, same Bash call):
- `✅` -> tick its `Collect <name>` item `[x]`; an `(inferred)` check only means the agent stopped, read its result first.
- `⏳` -> still running; wait for its completion notice, do not re-dispatch.
- `❌` -> add the printed `- [ ] Chase ...` line to the todo list and handle it this turn.
- `Pending dispatch` -> the user already asked: dispatch it in this reply without asking.

## Step 4 — Confirm

```
✅ Woke from <hash> (<date time>)
Task: [one-line summary from ## Task]
[## Awaiting Reply items, if present, listed first, as written]
[📅/⚠️ Due line, only if the checkpoint has a ## Due section]

✅ N items done (type "expand" to view)

Next steps:
- [ ] [each still-open item from ## Next Steps, as written]

[## Decisions / Watch section, if present, in full]
```

- Show only open `[ ]` items; fold `[x]` and `[-] dropped` items into the `✅ N items done` line; expand only on request. If nothing is checked, omit the done line.
- Always print `## Decisions / Watch` in full after the todo list; it is never collapsed.
- Do not print other checkpoint content again.
