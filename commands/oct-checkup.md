---
description: "Checkup: list per-call token/cost details for this session; `habits` scans recent sessions for waste patterns and suggests rules worth saving as memory; `nap-timing` uses your own history to compute how often to nap/clear for each model; `baseline` shows your rolling no-nap cost baseline and break-even; `memory` finds duplicate/stale/contradicting memory notes"
---

# oct-checkup

```bash
/oct-checkup                # Current session, table view
/oct-checkup --current      # Current session + context size estimate
/oct-checkup --detail       # Add tier/speed/geo/web columns
/oct-checkup --summary      # Aggregated totals by token type
/oct-checkup <session-id>   # Specific session (partial ID ok)
/oct-checkup --last=N       # Last N calls only
/oct-checkup habits         # Waste patterns in the last 7 days + suggested rules
/oct-checkup habits 30      # ...over the last 30 days
/oct-checkup nap-timing     # Per-model nap/clear sweet-spot, all-time history
/oct-checkup nap-timing 30  # ...over the last 30 days
/oct-checkup why            # Why estimated savings are low
/oct-checkup report         # The 2-3 line 7-day summary the first run prints automatically
/oct-checkup baseline       # Rolling no-nap baseline, cold-start cost, break-even context
/oct-checkup memory         # Scan MEMORY.md + memory files for duplicates / stale / contradictions
```

## Finding the script

Every command below is `$PY "$SCRIPT" ...`. Put this at the top of the same Bash call:

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
CORE="${CLAUDE_PLUGIN_ROOT}/scripts/oct_core.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
```

## Table (default, `--current`, `--detail`, `--summary`, `<session-id>`, `--last=N`)

Run `$PY "$SCRIPT" --last=20 --reverse` for the current session table, or `$PY "$SCRIPT"` (no args) to list all sessions. Pass the user's flags/session id through to the script (`--current`, `--detail`, `--summary`, `<session-id>`, `--last=N`).

Columns: In (fresh input), CacheRead, CacheWrite, Out, Cost (USD, per-model pricing). `--detail` adds `1h`, `5m`, `🔍` (web search), `🌐` (web fetch), `Tier`, `Speed`.

Then read the saved output file if truncated and print the FULL content as a plain code block in the response (the user must see the table in chat, not just the Bash result).

If the header shows more than 20 calls in total, append after the code block: "(Showing the latest 20 of N calls. Use `--last=50` to see more.)"

## Habits (`/oct-checkup habits [days]`)

```bash
$PY "$SCRIPT" --habits            # 7 days
$PY "$SCRIPT" --habits --days=30
```

Print the report as-is in a code block. It ends with a question about which suggestions to save; wait for the answer.

For each accepted suggestion, write a feedback memory into the project's memory directory (named in the system prompt's auto-memory section; `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/memory/`): frontmatter `name` / `description` / `metadata.type: feedback`, then the rule, a **Why:** line citing the pattern and its cost from the report, and a **How to apply:** line; add a one-line pointer to `MEMORY.md`. If a memory for the same rule exists, update it instead of duplicating.

Confirm only: `✅ Saved: <name>, <name>` (do not echo the memory content). If the user declines all, say nothing more. If the report says no patterns were found, that is the whole answer.

## Nap Timing (`/oct-checkup nap-timing [days]`)

```bash
$PY "$SCRIPT" --nap-timing
$PY "$SCRIPT" --nap-timing --days=30
```

Print the report as-is in a code block, including its `Suggested nudge_growth_tokens` line; no follow-up question. If it says samples are too thin, that is the whole answer (do not fabricate a number).

## Why (`/oct-checkup why`)

```bash
$PY "$SCRIPT" --savings-why
```

Print the report as-is in a code block, then one sentence in the user's language for the `Main:` cause and its suggestion. Causes: (e) nap_nudge or auto_wake off; (a) reminders shown but few nap/clear; (b) sessions already as short as before install, so the value is auto-resume after /clear; (c) growth never reached nudge_growth_tokens, with a suggested value; (d) no duplicate reads. No follow-up question.

## Report (`/oct-checkup report`)

```bash
CORE="${CLAUDE_PLUGIN_ROOT}/scripts/oct_core.py"
$PY "$CORE" report --cwd="$PWD"
```

Print the output as-is in a code block. No follow-up question. (The same lines are printed automatically once, by script, on the first run after install; no model tokens.)

## Baseline (`/oct-checkup baseline`)

```bash
$PY "$CORE" baseline
```

Print as-is in a code block, then one sentence in the user's language: the break-even context for their usual session length, and that the net saving already subtracts the cold-start cost of the fresh session after `/clear`. If a model says "too few for a $ estimate", say so instead of inventing a number. Window sizes and thresholds are in `oct-toolkit.json` (`baseline_window_sessions`, `baseline_window_days`, `baseline_min_sessions`, `nudge_min_net_usd`).

## Memory (`/oct-checkup memory`)

1. Inventory (also tells you the memory directory; slug rule as in `/oct-wake`):

```bash
$PY "$CORE" memory-scan --cwd="$PWD"
```

2. Spawn one background cold agent: `subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`, `description: "scan memory"`. Prompt: "Read-only. Read <dir>/MEMORY.md and every memory file it links. Find (a) duplicates or near-duplicates, (b) stale or finished notes (dated, resolved, superseded), (c) contradictions between notes, (d) MEMORY.md lines that no longer match their file. Do not edit or delete anything. Reply with a numbered list; per item: the files involved, the problem in one line, and the proposed action (merge into X / move to archive/ / fix the index line / ask which of two is right). End with the line count of MEMORY.md before and after if all were applied."
3. When it finishes, show the list and let the user pick items by number (one question, multi-select). Do nothing for unpicked items.
4. Apply only the picked items. Merge keeps every distinct fact; "stale" means move to `<dir>/archive/`, never delete; contradictions are resolved by asking, not guessing. Never auto-delete.
5. Record the check, whatever was picked: `$PY "$CORE" memory-mark --cwd="$PWD"`. Confirm in one line: `✅ Memory checked: N applied, M skipped`.
