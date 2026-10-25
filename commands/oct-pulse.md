---
description: "Pulse: persistent status bar (model + per-window 5h/7d icon + projected runway + ctx%; re-run this command for the full bar detail) + per-response cost; enable/disable toggle"
---

# oct-pulse

Status bar (model, per-window rate-limit icon + runway, ctx%) plus a per-response cost line.

```bash
/oct-pulse           # Not wired yet: check + offer to wire. Already wired: show current detail.
/oct-pulse enable    # Wire both (status bar + per-response cost line)
/oct-pulse disable   # Remove both
/oct-pulse savings off|on   # Hide/show the savings badge and the weekly savings sentence
```

Surfaces:
- After each response (Stop hook, `--watch`): `💰 In:2($0.00)  CR:57.9K($0.02)  CW:837($0.00)  Out:123($0.00)  =$0.0224`
- Status bar (statusLine hook, `--statusline-hook`; needs Claude Code >= 2.1.80; state cached in `${CLAUDE_CONFIG_DIR:-~/.claude}/scripts/rate-limits-state.json`): `Sonnet 5  5h 30m🔋2.2h  7d 2.0d🪫20.5h  🧠79%`
  - Per window: reset countdown, icon, projected runway. 🔋 runway >= reset; ⚡ burning ahead of schedule; 🪫 burning far ahead of schedule.
  - `✨` after the 7d runway: quota piling up unused.
  - `🧠`ctx%; trailing `💡` means ctx is high enough that a cold resume would be expensive (run `/oct-nap`).
- `--pulse-detail` prints a verdict line, ctx%, and one bar per window, e.g.:
  ```
  🪫 A window is burning far faster than schedule; slow down right away
  ctx:79%
  5h 80%│──3.3h🔋  7d 87%🪫20.5h─│
  ```
  `⏳`/`⏳5m` = still gathering history, `∞` = usage flat; neither means "on schedule". If the cache is stale (statusLine has not fired in 30 min) it says so.

## Step 0 — Script path

`SCRIPT` is `${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py`. Write it with `~` rather than `/home/<user>` so settings stay portable. `PY` is the first of `python3`, `python`, `py -3` that runs (`PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)`); use it in place of `python3` in every command below, including the ones written to settings.

`SHIM` is `${CLAUDE_CONFIG_DIR:-~/.claude}/oct-toolkit/statusline.py`, rewritten by the plugin's SessionStart hook on every startup to point at the installed version, so it survives upgrades.

## Status check (no args)

Check `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json`:
- Status bar: `statusLine.command` contains `statusline.py` or `usage-analyze.py`.
- Per-response line: `hooks.Stop` has an entry containing `--watch`, or the plugin is installed as a plugin (its `hooks/hooks.json` registers that Stop hook; look for `hooks/hooks.json` next to `SCRIPT`'s parent directory).

Report both and offer to fix what is missing:

```
🫀 oct-pulse
   Status bar (model/ctx%/quota): ❌ not wired
   Per-response cost: ✅ wired (plugin hook)

Want me to wire up the status bar? (It writes the statusLine entry in ${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json)
```

If both are wired, run `PY SCRIPT --pulse-detail`, show its output as-is, and stop. If it says there is no data yet, say so instead of re-running.

## Enable (or "yes" to the offer)

Status bar: if `statusLine` is absent, set it:

```json
"statusLine": {
  "type": "command",
  "command": "PY SHIM"
}
```

Write `SHIM` with `~` (or the resolved directory if `CLAUDE_CONFIG_DIR` is set). If `SHIM` does not exist (clone install, no hook has run), use `PY SCRIPT --statusline-hook` instead.

If a different `statusLine` exists, show it and ask before replacing.

Per-response line: only if not already active via plugin hook, add to `hooks.Stop`:

```json
{
  "type": "command",
  "command": "PY -c \"import sys,json,subprocess,time,os; time.sleep(1); r=subprocess.run(['PY',os.path.expanduser('SCRIPT'),'--watch'],capture_output=True,text=True); print(json.dumps({'systemMessage':r.stdout.strip()}))\""
}
```

Write back and confirm with:
```
✅ oct-pulse is wired. The status bar will appear after the next reply.
If you see an icon or number you don't understand, just ask me instead of guessing.
```

## Disable

Remove the `statusLine` entry only if its command contains `statusline.py` or `usage-analyze.py`. Remove any `hooks.Stop` entry containing `--watch`. Plugin-registered hooks cannot be removed here; say so if that is the only one. Confirm:
```
✅ oct-pulse is off.
```

## Savings off|on

Edit `${CLAUDE_CONFIG_DIR:-~/.claude}/oct-toolkit.json` (create if missing, keep other keys): set `savings_badge` and `weekly_savings` to `false` for `off`, `true` for `on`. Confirm in one line.
