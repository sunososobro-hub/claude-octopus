---
description: 脈搏：常駐狀態列（模型/ctx%/5h+7d 額度/會不會在 reset 前燒完）+ 每回合花費；enable/disable 開關
---

# oct-pulse

Live vitals: a persistent status bar (model, ctx%, 5h/7d quota) plus a
per-response cost line. Run it once with no arguments after installing —
it checks what's wired, and offers to wire what isn't.

## Usage

```bash
/oct-pulse           # Check both surfaces; offer to wire anything missing
/oct-pulse enable    # Wire both (status bar + per-response cost line)
/oct-pulse disable   # Remove both
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
next to it: `ctx:57%  💡ctx偏高,收工前建議/oct-nap`. Reason: prompt
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

### Step 0 — Find the script

Everything below needs the absolute path of `usage-analyze.py`. Check in
order and use the first that exists:

1. `~/.claude/scripts/usage-analyze.py` (manual install)
2. `~/.claude/skills/*/scripts/usage-analyze.py` (skills-dir plugin clone — the documented install path)
3. `~/.claude/plugins/*/scripts/usage-analyze.py` (legacy/manual plugins-dir clone, if someone did that anyway)
4. `find ~/.claude -name usage-analyze.py 2>/dev/null | head -1` (marketplace cache)

Call it `SCRIPT` below. Write it with `~` rather than `/home/<user>` so
the settings file stays portable.

### Status check (no args)

Two things to check in `~/.claude/settings.json`:

- **Status bar**: `statusLine.command` contains `usage-analyze.py`.
- **Per-response line**: either `hooks.Stop` has an entry containing
  `--watch`, **or** the plugin was installed as a plugin (its
  `hooks/hooks.json` registers that Stop hook automatically — look for
  `hooks/hooks.json` next to `SCRIPT`'s parent directory).

Report both, then offer to fix whatever's missing — don't make the user
type a second command:

```
🫀 oct-pulse
   狀態列（模型/ctx%/額度）：❌ 未接
   每回合花費：✅ 已接（plugin hook）

要我幫你把狀態列接上嗎？（會寫進 ~/.claude/settings.json 的 statusLine）
```

If both are ✅, say so in one line and stop.

### Enable (or "yes" to the offer above)

**Status bar** — if `statusLine` is absent, set it:

```json
"statusLine": {
  "type": "command",
  "command": "python3 SCRIPT --statusline-hook"
}
```

If a *different* `statusLine` is already there, show it and ask before
replacing — it's a singleton and might be the user's own.

**Per-response line** — only if not already active via plugin hook, add
to `hooks.Stop`:

```json
{
  "type": "command",
  "command": "python3 -c \"import sys,json,subprocess,time,os; time.sleep(1); r=subprocess.run(['python3',os.path.expanduser('SCRIPT'),'--watch'],capture_output=True,text=True); print(json.dumps({'systemMessage':r.stdout.strip()}))\""
}
```

Write back and confirm:
```
✅ oct-pulse 已接上。狀態列會在下一次回覆後出現。
```

### Disable

Remove the `statusLine` entry only if its command contains
`usage-analyze.py` (never remove someone else's), and remove any
`hooks.Stop` entry containing `--watch`. Plugin-registered hooks can't be
removed here — say so if that's the only one. Confirm:
```
✅ oct-pulse 已關閉。
```
