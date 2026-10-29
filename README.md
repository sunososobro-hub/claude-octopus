# oct-toolkit

Install, then just /clear when reminded — everything else runs in the background.

Claude Code plugin: nap/wake session handoff, memory tidy, duplicate-read guard, and 5h/7d rate-limit status bar.

## Install

As a Claude Code plugin (commands and hooks both load):

```bash
claude plugin marketplace add sunososobro-hub/claude-octopus
claude plugin install oct-toolkit@oct-toolkit
```

Or inside a session: `/plugin marketplace add sunososobro-hub/claude-octopus`, then `/plugin install oct-toolkit@oct-toolkit`. Restart Claude Code afterwards.

Commands are namespaced when installed as a plugin: `/oct-toolkit:oct-nap`, `/oct-toolkit:oct-wake`, `/oct-toolkit:oct-pulse`, `/oct-toolkit:oct-checkup`, `/oct-toolkit:oct-consult`. Update with `claude plugin update oct-toolkit@oct-toolkit`.

Commands-only alternative (no hooks, so no auto-wake, nap nudge, cost line or read guard):

```bash
git clone https://github.com/sunososobro-hub/claude-octopus ~/.claude/skills/oct-toolkit
```

Then run `/oct-toolkit:oct-pulse` (plugin) or `/oct-pulse` (clone) and answer yes to wire the status bar. It writes a `statusLine` entry running `usage-analyze.py --statusline-hook` (through a shim that follows plugin upgrades) to `~/.claude/settings.json`.

Requires Python 3 (`python3`, `python` or `py -3`) and Claude Code >= 2.1.80 (rate limits).

## Commands

Shown un-prefixed; add `oct-toolkit:` when installed as a plugin.

- `/oct-nap` - save a checkpoint; carries open items forward and archives older ones of the same project
- `/oct-wake` - load a checkpoint or search long-term memory
- `/oct-pulse` - status bar and per-response cost line
- `/oct-checkup` - per-call token/cost table, `habits`, `nap-timing`, `report`, `baseline`, `memory`
- `/oct-consult` - second opinion from a cold sub-agent

## Automatic behavior & cost

| What runs | When | Approx. tokens |
|---|---|---|
| Nap nudge (`nap-nudge.py`) | when a nap + `/clear` now would save more than `nudge_min_net_usd` (default $0.02) **net of the cold-start cost**, judged from your own history (see below), then at most every 15 turns; until your history is thick enough it falls back to 30 user turns or `nudge_growth_tokens` (default 80000) of growth; asks Claude to nap in the background | one line |
| Background nap | a forked subagent writes the checkpoint, merges and archives same-project ones, prints the savings line; your turn is not blocked | fork re-reads the cached context (cache reads, no cache miss); roughly +25% over a foreground nap at ~40k context, see below |
| Clear reminder | ~5 turns after a nap without `/clear`, one line, once per nap | one line |
| Memory tidy | after a nap, only if `MEMORY.md` has more than 40 lines: a background subagent merges duplicates and archives stale notes, prints `tidying memory in background` | reads memory files only |
| Auto-wake (`auto-wake.py`) | after `/clear`, injects the latest checkpoint of the project | ~1-2k per `/clear` |
| Cost line (Stop hook) | after each response, shown as a systemMessage | 0 model tokens |
| Startup nudge (`wake-nudge.py`) | new session, reminds of an unresumed checkpoint; warns once when `MEMORY.md` is bloated or unchecked for 30 days | 0 model tokens |
| First checkup (`oct_core.py`) | automatically on the first run (no `oct-toolkit/checkup.json` yet): a background script reads your transcripts and prints 2-3 lines once; with under 3 days / 3 sessions of history it says so and retries every 6 h | 0 model tokens |
| Read guard (`read-dedup.py`) | blocks re-reading an unchanged file in the same session; cache files in the system temp dir, deleted after 1 day | 0 |

Measured on a ~40k context (sonnet): foreground nap, 3 calls, $0.120, main turn 28.8 s; background nap, fork 5 calls all cache-read, total $0.150, main turn 6.4 s. If the fork or background runs are unavailable the nap runs in the foreground.

`/oct-nap` ends with a line such as `nap: context ~80k → ~2k after /clear (~97% less per turn)`.

Turn each off in `~/.claude/oct-toolkit.json` (all default to `true`):

```json
{"auto_wake": false, "nap_nudge": false, "clear_reminder": false, "memory_tidy": false, "cost_line": false, "first_checkup": false, "memory_check": false, "nudge_dynamic": false}
```

## First checkup

No questions asked. On the first session after install the plugin runs a script (no model, no cost) over your last 7 days of transcripts and prints, once, something like:

```
oct-toolkit checkup (7 days): about $41 API-equivalent across 38 sessions; 63% of it is re-reading long conversations (CR, cache reads).
MEMORY.md is 112 lines (~2.4k tokens) - over the 80-line limit; napping about every 24 turns pays off for you (sonnet-5-5).
For details run /oct-checkup.
```

With fewer than 3 days or 3 sessions of history it prints only "installed, first report after a few days of use" and tries again automatically. Dollar figures are API-equivalent list prices, not your bill. Run `/oct-checkup report` any time.

## Net savings and the rolling baseline

A nap only pays when the context you drop is worth more than the cold start of the fresh session. The plugin measures both from your own transcripts (no-nap sessions only, entrypoint `cli`, nap/auto-wake sessions excluded), as a moving average over your newest `baseline_window_sessions` (default 30, at most `baseline_window_days` = 60 days old) sessions per model, refreshed in the background every 6 h:

- cold start = mean cache-write cost of a session's first 3 calls (priced at the 1h/5m rates actually used) + the checkpoint (~2k tokens at the cache-write price); cold size = context after those 3 calls.
- expected remaining calls = median of (session length - calls so far) over your window sessions that ran longer; with fewer than 5 such sessions it assumes a conservative `nap_fallback_remaining` (10) calls.
- net saving = (context - cold size - checkpoint) x cache-read price x remaining calls - cold-start cost.

`/oct-nap` prints it as an `estimate:` line (it can be negative, and says so); the nap reminder fires only when net > `nudge_min_net_usd`. With fewer than `baseline_min_sessions` (5) comparable sessions for the model no dollar figure is shown. Setting `nudge_growth_tokens` explicitly in the config also keeps the old fixed growth trigger. `/oct-checkup baseline` prints your numbers and break-even context.

## Memory check

At session start a script checks `MEMORY.md` of the current project (`~/.claude/projects/<slug>/memory/`, slug = working directory with every non-alphanumeric character replaced by `-`). One line, once per trigger, when it exceeds `memory_max_lines` (80) or `memory_max_tokens` (3000, about 4 characters each), or when `memory_check_days` (30) have passed since the last check. `/oct-checkup memory` sends a background Sonnet agent to read the notes (read-only), lists duplicates, stale notes and contradictions, and you pick what to apply; nothing is deleted without your pick, stale notes move to `memory/archive/`.

Estimated savings badge in the status bar, as a percent against the no-oct estimate (actual spend + estimated saving), over the last 5 hours (same as the Claude 5h quota window), with the 7-day figure in brackets: `🐙 -12% 5h (7d -8%)`. `-12%` means about 12% less spend than without oct; `~0%` means under 1%. The estimate is counterfactual and never negative, so there is no `+`. Fallbacks: fewer than 10 turns or under $0.05 spend in the 5h window shows the 7-day figure only (`🐙 -8% 7d`); fewer than 50 turns in 7 days, or savings under $0.01, hides the badge and the weekly sentence names the main cause (also `/oct-checkup why`). Turn off with `/oct-pulse savings off` or `"savings_badge": false, "weekly_savings": false`.

`nudge_growth_tokens` (number, default 80000) is the growth threshold used until the baseline is ready, or always when set explicitly; `/oct-checkup nap-timing` suggests a value. Other numeric keys: `baseline_window_sessions`, `baseline_window_days`, `baseline_min_sessions`, `nudge_min_net_usd`, `nap_fallback_remaining`, `memory_max_lines`, `memory_max_tokens`, `memory_check_days`, `checkup_min_days`, `checkup_min_sessions`.

`auto_wake` also covers the startup nudge. Honors `CLAUDE_CONFIG_DIR`.

## Permissions

Plugins cannot ship permission allow rules (plugin `settings.json` honors only `agent` and `subagentStatusLine`), so Claude Code asks once the first time a command runs the plugin's Python scripts. Choose "always allow" to stop the prompt; or add `Bash(python3 *)` to `permissions.allow` in your own settings.

## License

MIT
