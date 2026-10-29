---
description: "Pulse: status bar (model, 5h/7d icon + runway, ctx%) and per-response cost; enable/disable; run bare for detail"
---

# oct-pulse

Args: none (not wired: check + offer to wire; wired: show detail); `enable` (wire status bar + per-response cost line); `disable` (remove both); `savings off|on` (hide/show savings badge and weekly savings sentence).

Surfaces:
- After each response (Stop hook, `--watch`): `💰 In:2($0.00)  CR:57.9K($0.02)  CW:837($0.00)  Out:123($0.00)  =$0.0224`
- Status bar (statusLine hook `--statusline-hook`; needs Claude Code >= 2.1.80; state cached in `${CLAUDE_CONFIG_DIR:-~/.claude}/scripts/rate-limits-state.json`): `Sonnet 5  5h 30m🔋2.2h  7d 2.0d🪫20.5h  🧠79%`
  - Per window: reset countdown, icon, projected runway. 🔋 runway >= reset; ⚡ burning ahead of schedule; 🪫 far ahead of schedule. `✨` after the 7d runway: quota piling up unused.
  - `🧠`ctx%; trailing `💡` = ctx high enough that a cold resume would be expensive (run `/oct-nap`).
- `--pulse-detail` prints a verdict line, ctx%, one bar per window:
  ```
  🪫 A window is burning far faster than schedule; slow down right away
  ctx:79%
  5h 80%│──3.3h🔋  7d 87%🪫20.5h─│
  ```
  `⏳`/`⏳5m` = still gathering history, `∞` = usage flat; neither means "on schedule". Says so if the cache is stale (statusLine silent for 30 min).

## Step 0 — Paths

`SCRIPT` = `${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py`; write it with `~`, not `/home/<user>`, so settings stay portable. `PY` = first of `python3`, `python`, `py -3` that runs (`PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)`); use it instead of `python3` in every command below, including those written to settings.

`SHIM` = `${CLAUDE_CONFIG_DIR:-~/.claude}/oct-toolkit/statusline.py`, rewritten by the SessionStart hook on every startup to point at the installed version, so it survives upgrades.

## Status check (no args)

Check `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json`:
- Status bar: `statusLine.command` contains `statusline.py` or `usage-analyze.py`.
- Per-response line: `hooks.Stop` has an entry containing `--watch`, or the plugin registers it (`hooks/hooks.json` next to `SCRIPT`'s parent dir).

Report both, offer to fix what is missing:

```
🫀 oct-pulse
   Status bar (model/ctx%/quota): ❌ not wired
   Per-response cost: ✅ wired (plugin hook)

Want me to wire up the status bar? (It writes the statusLine entry in ${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json)
```

Both wired: run `PY SCRIPT --pulse-detail`, show as-is, stop. If it says no data yet, say so; do not re-run.

## Enable (or "yes" to the offer)

Status bar: if `statusLine` is absent set `"statusLine": {"type": "command", "command": "PY SHIM"}`. Write `SHIM` with `~` (or the resolved dir if `CLAUDE_CONFIG_DIR` is set). If `SHIM` does not exist (clone install, no hook has run) use `PY SCRIPT --statusline-hook` instead. If a different `statusLine` exists, show it and ask before replacing.

Per-response line: only if not already active via plugin hook, add to `hooks.Stop`:

```json
{
  "type": "command",
  "command": "PY -c \"import sys,json,subprocess,time,os; time.sleep(1); r=subprocess.run(['PY',os.path.expanduser('SCRIPT'),'--watch'],capture_output=True,text=True); print(json.dumps({'systemMessage':r.stdout.strip()}))\""
}
```

Write back and confirm:
```
✅ oct-pulse is wired. The status bar will appear after the next reply.
If you see an icon or number you don't understand, just ask me instead of guessing.
```

## Disable

Remove the `statusLine` entry only if its command contains `statusline.py` or `usage-analyze.py`; remove any `hooks.Stop` entry containing `--watch`. Plugin-registered hooks cannot be removed here; say so if that is the only one. Confirm: `✅ oct-pulse is off.`

## Savings off|on

Edit `${CLAUDE_CONFIG_DIR:-~/.claude}/oct-toolkit.json` (create if missing, keep other keys): `savings_badge` and `weekly_savings` = `false` for `off`, `true` for `on`. Confirm in one line.
