# oct-watch

Show per-response token usage after every Claude response (Stop hook).

## Usage

```bash
/oct-watch           # Show current status (enabled/disabled)
/oct-watch enable    # Add Stop hook → show usage after each response
/oct-watch disable   # Remove Stop hook
```

## Output (when enabled)

Two separate surfaces, deliberately not duplicating each other:

**After each response** (Stop hook) — that call's own token/cost breakdown,
nothing else (no model name, no ctx%, no rate-limit info):
```
💰 In:2($0.00)  CR:57.9K($0.02)  CW:837($0.00)  Out:123($0.00)  =$0.0224
```

**Bottom status bar** (statusLine hook, always visible) — model name,
context-window %, and rate-limit health, since Claude Code reserves that
row whenever a `statusLine` hook is configured at all, so it's better used
than left blank. This is the *only* place model name and `ctx%` appear
now — both used to be duplicated in the Stop hook line above (ctx% via our
own model→context-size guess table, which could and did disagree with
Claude Code's own official number by a point or two). Deleted the guess
table, kept the official one.

When `ctx%` crosses 50% (`_CTX_NUDGE_THRESHOLD`), a nudge appears right
next to it: `ctx:57%  💡ctx偏高,收工前建議/oct-save`. Reason: prompt
cache TTL is ~1h — a large context left idle past that (end of day,
switching tasks) means whoever resumes it eats a full cold reprocess
(`cache_write` on everything, not cheap `cache_read`) — exactly what the
`--resume` A/B tests measured as the expensive path. There's no way to
detect "about to step away" directly, so the nudge just stays visible
whenever ctx is already big enough that a cold resume would actually
hurt, however the session ends up pausing:
```
Sonnet 5  ctx:38%  5h視窗:40%  reset:1.2h / 可撐:9.7h  |  7d:5%  reset:5.8d / 可撐:採樣中,還需48m
```

`reset:X / 可撐:Y` puts the natural reset countdown right next to "how
much longer can I keep going at this pace" so they're directly
comparable: `reset:1.2h / 可撐:10.0h` (window empties out on its own
before you'd hit the cap — the normal case, no marker) vs `reset:75m /
可撐:3m ⚠️會先燒完` (you'd hit the cap *before* the natural reset —
flagged because it's the case actually worth noticing). Deliberately not
called "ETA" — that reads as "time of arrival," not "how long you can
sustain this," which is what the number actually answers. Durations
auto-scale (m/h/d). The same treatment applies to the 7-day window, with
its own pacing since a week moves ~100x slower than 5h: samples hourly
(not every 60s), keeps 48h of history (not 20min), needs 2h of real
spread (not 3min) before trusting a rate.

This is all built on Anthropic's **official** `rate_limits.five_hour` /
`seven_day` (`used_percentage`, `resets_at`), captured by the
`statusLine` hook (`--statusline-hook`, requires Claude Code ≥2.1.80) and
cached in `~/.claude/scripts/rate-limits-state.json`. There
is no self-calibrated fallback anymore — official data has proven
reliably available in practice, and a guessed number wasn't worth the
complexity. If the cache is stale (statusLine hasn't fired in 30 min,
e.g. right after enabling, or on an older Claude Code), the reset/可撐
segment just doesn't appear rather than showing something made up.

### Enable (updated — also wires the statusLine hook)

Also set `statusLine` in `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 ~/.claude/scripts/usage-analyze.py --statusline-hook"
}
```

(Skip this if the user already has a different statusLine configured — ask
before overwriting it.)

## How It Works

### Status check (no args)

Read `~/.claude/settings.json`. Check if `hooks.Stop` contains an entry with `--watch`.

If enabled:
```
⌚ oct-watch  enabled
   Stop hook: active — usage shown after each response
   Disable: /oct-watch disable
```

If disabled:
```
⌚ oct-watch  disabled
   Enable: /oct-watch enable
```

### Enable

Read `~/.claude/settings.json`. Add to `hooks.Stop`:

```json
{
  "type": "command",
  "command": "python3 -c \"import sys,json,subprocess,time,os; time.sleep(1); r=subprocess.run(['python3',os.path.expanduser('~/.claude/scripts/usage-analyze.py'),'--watch'],capture_output=True,text=True); print(json.dumps({'systemMessage':r.stdout.strip()}))\""
}
```

Write back and confirm:
```
✅ oct-watch enabled — usage will appear after each response.
```

### Disable

Read `~/.claude/settings.json`. Remove any entry in `hooks.Stop` that contains `--watch`. Write back and confirm:
```
✅ oct-watch disabled.
```
