---
description: "Checkup: per-call token/cost table for this session; subcommands habits, nap-timing, why, report, baseline, memory"
---

# oct-checkup

Args: none (current session table); `--current` (+ context size estimate); `--detail` (adds tier/speed/geo/web columns); `--summary` (totals by token type); `<session-id>` (partial ok); `--last=N`; `habits [days]` (waste patterns, default 7d, + suggested rules); `nap-timing [days]` (per-model nap/clear sweet spot, default all-time); `why` (why estimated savings are low); `report` (the 7-day summary printed automatically on first run); `baseline` (rolling no-nap baseline, cold-start cost, break-even); `memory` (MEMORY.md duplicates/stale/contradictions).

Setup (prefix every Bash call; commands below are `$PY "$SCRIPT" ...` or `$PY "$CORE" ...`):

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
CORE="${CLAUDE_PLUGIN_ROOT}/scripts/oct_core.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
```

Unless stated, print script output as-is in a code block and ask no follow-up.

## Table (default and the flags above)

`$PY "$SCRIPT" --last=20 --reverse` for the current session, or `$PY "$SCRIPT"` to list all sessions; pass the user's flags/session id through (`--current`, `--detail`, `--summary`, `<session-id>`, `--last=N`).

Columns: In (fresh input), CacheRead, CacheWrite, Out, Cost (USD, per-model pricing); `--detail` adds `1h`, `5m`, `🔍` (web search), `🌐` (web fetch), `Tier`, `Speed`.

Read the saved output file if truncated and print the FULL content as a code block in the response (the user must see it in chat, not just the Bash result). If the header shows more than 20 calls, append: "(Showing the latest 20 of N calls. Use `--last=50` to see more.)"

## Habits

`$PY "$SCRIPT" --habits` (7 days) or `--habits --days=30`. The report ends with a question about which suggestions to save; wait for the answer.

For each accepted suggestion write a feedback memory in the project's memory dir (system prompt auto-memory section; `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/memory/`): frontmatter `name` / `description` / `metadata.type: feedback`, then the rule, a **Why:** line citing the pattern and its cost from the report, and a **How to apply:** line; add a one-line pointer to `MEMORY.md`. If a memory for the same rule exists, update it.

Confirm only: `✅ Saved: <name>, <name>` (no content echo). All declined: say nothing more. No patterns found: that is the whole answer.

## Nap Timing

`$PY "$SCRIPT" --nap-timing` or `--nap-timing --days=30`. Include its `Suggested nudge_growth_tokens` line. If samples are too thin, that is the whole answer (no invented number).

## Why

`$PY "$SCRIPT" --savings-why`; then one sentence in the user's language for the `Main:` cause and its suggestion. Causes: (e) nap_nudge or auto_wake off; (a) reminders shown but few nap/clear; (b) sessions already as short as before install, value is auto-resume after /clear; (c) growth never reached nudge_growth_tokens, with a suggested value; (d) no duplicate reads.

## Report

`$PY "$CORE" report --cwd="$PWD"`. (Also printed once by script on the first run after install; no model tokens.)

## Baseline

`$PY "$CORE" baseline`; then one sentence in the user's language: the break-even context for their usual session length, and that the net saving already subtracts the fresh session's cold-start cost after `/clear`. If a model says "too few for a $ estimate", say so, no invented number. Thresholds live in `oct-toolkit.json` (`baseline_window_sessions`, `baseline_window_days`, `baseline_min_sessions`, `nudge_min_net_usd`).

## Memory

1. Inventory (also gives the memory dir; slug rule as in `/oct-wake`): `$PY "$CORE" memory-scan --cwd="$PWD"`
2. Spawn one background cold agent: `subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`, `description: "scan memory"`. Prompt: "Read-only. Read <dir>/MEMORY.md and every memory file it links. Find (a) duplicates or near-duplicates, (b) stale or finished notes (dated, resolved, superseded), (c) contradictions between notes, (d) MEMORY.md lines that no longer match their file. Do not edit or delete anything. Reply with a numbered list; per item: the files involved, the problem in one line, and the proposed action (merge into X / move to archive/ / fix the index line / ask which of two is right). End with the line count of MEMORY.md before and after if all were applied."
3. When done, show the list; the user picks by number (one multi-select question). Do nothing for unpicked items.
4. Apply only picked items. Merge keeps every distinct fact; stale = move to `<dir>/archive/`, never delete; contradictions are resolved by asking. Never auto-delete.
5. Whatever was picked, record the check: `$PY "$CORE" memory-mark --cwd="$PWD"`. Confirm in one line: `✅ Memory checked: N applied, M skipped`.
