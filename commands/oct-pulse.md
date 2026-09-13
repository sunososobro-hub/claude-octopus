---
description: 脈搏：常駐狀態列（模型+5h/7d 各自的圖示+可撐時間+ctx%，重跑本指令展開完整 bar 細節）+ 每回合花費；enable/disable 開關
---

# oct-pulse

Live vitals: a persistent status bar (model name, each rate-limit
window's own icon + 可撐 duration, and ctx%) plus a per-response cost
line. Run it once with no arguments after installing — it checks what's
wired, and offers to wire what isn't. Once both are wired, running it
again with no arguments instead expands into the full bar view — a
terminal statusLine can't be clicked, so re-running the command *is* "tap
for detail".

## Usage

```bash
/oct-pulse           # Not wired yet: check + offer to wire. Already wired: show current detail.
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

**Bottom status bar** (statusLine hook, always visible) — model name plus
each rate-limit window's own icon between two numbers *in the same unit*
(reset countdown / 可撐 duration), plus ctx%, since Claude Code reserves
that row whenever a `statusLine` hook is configured at all, so it's
better used than left blank:
```
Sonnet 5  5h 30m🔋2.2h  7d 2.0d🪫20.5h  🧠79%
```
Three independent readouts, deliberately not collapsed into one icon —
"one battery, no idea when it'll actually run out" was exactly the
problem with an earlier, more compressed version of this line; and pct%
next to a duration (a version that briefly existed in between) forced a
unit conversion in the reader's head to see what the icon already knows:

- **`5h`/`7d` + `reset` + icon + `可撐`** — for *each* window: is the
  current burn rate on schedule to empty the quota right around its
  natural reset, or well before it? Both flanking numbers are durations —
  reset (time left until the window resets) on the left, 可撐 (projected
  time-to-100%-used) on the right, icon in between instead of a separator
  — on purpose, so the comparison the icon already made is checkable by
  eye instead of taken on faith. 🔋 = 可撐 ≥ reset (safe, cushion). ⚡ =
  burning ahead of schedule but by less than half the balance point. 🪫 =
  burning ahead by more than half — heading for empty well before reset.
  Gated on usage > 60% (below that a rate projection this far out is too
  noisy to act on), *and* on the absolute shortfall (reset − 可撐) being
  at least 15 minutes — close to a reset, a small window means even a
  scary-looking % deficit is only a few real minutes of lockout (reset in
  1h, 可撐 50min is −17% by fraction but only 10 real minutes), not worth
  a warning; far from reset the same fraction is a much bigger absolute
  gap and still fires normally. Under either gate it's always 🔋
  regardless of the raw number.

  可撐 is actually the *more conservative* (safer-looking) of two signals,
  not one: a **recent-pace** projection (last 20min for 5h, last 48h for
  7d — reactive, but noisy: a short burst alone can make it look
  alarming) and an **average-pace-since-window-start** projection (pct ÷
  elapsed time — needs no history at all, available from minute one, and
  naturally smooths out a busy morning or a quiet weekend since it's
  averaged over the whole window so far, not just the last few minutes).
  Taking the *longer* (safer) of the two means a brief spike the average
  absorbs doesn't trip 🪫 on its own, but a genuine sustained drift still
  gets caught even if the last few minutes happen to look calm. Both are
  still extrapolations, though, so 可撐 stays inherently backward-looking
  — neither signal can see a burst you're about to *start*. The official,
  never-wrong pct% (for whoever wants that as a separate sanity check
  instead of trusting the projection) is one `/oct-pulse` re-run away, in
  `--pulse-detail`.
- **`🧠`ctx%** — always shown, not only once it's high enough to matter
  (that was the other problem with the earlier version — no way to see
  ctx status at all most of the time). This is *not* the battery concept
  — ctx doesn't drain toward a reset, it's closer to short-term memory
  filling up: healthy is "not much loaded". A trailing `💡` means it's
  high enough (or growing fast enough) that a cold resume later would be
  expensive — Prompt cache TTL is ~1h, and a large context left idle past
  that (end of day, switching tasks) means whoever resumes it eats a full
  reprocess (`cache_write` on everything, not cheap `cache_read`) —
  exactly what the `--resume` A/B tests measured as the expensive path.
  There's no way to detect "about to step away" directly, so `💡` stays
  lit whenever ctx is already big enough that a cold resume would hurt,
  however the session ends up pausing.

This row is deliberately numbers-not-bars — the fuller bar view (dashes,
`│` center marks) is one more layer of detail than a glance needs, so it
lives behind a re-run instead: a terminal statusLine can't be clicked, so
"curious what this means, tap for detail" becomes **re-run `/oct-pulse`**
— see "If both are ✅" below. That detail view (`--pulse-detail`) prints
the headline verdict, ctx%, and one battery-style bar per rate-limit
window, e.g.:
```
🪫 有窗口燒得比排程快很多，得馬上放慢速度
ctx:79%
5h 80%│──3.3h🔋  7d 87%🪫20.5h─│
```
Each bar is center-anchored on the *schedule margin*, same numbers as the
compact line's icon+duration, just expanded: the 可撐 duration lives right
at the bar's tip, and the tip itself *is* the severity icon (🔋/⚡/🪫),
instead of a plain arrow with the number trailing separately. Bar grows
right of the center `│` when there's cushion (safe, tip 🔋). Grows left
when burning ahead of schedule, tip ⚡ or 🪫 depending how far past the
balance point — margin's danger side is naturally bounded in [-1, 0) (the
projected burn-out time can't go below 0), so "past half the balance
point" (-0.5) is a real threshold, not an arbitrary one. Dash count
mirrors the same magnitude, capped at 2 cells each direction — a
rough-magnitude cue, not a precise scale; the exact number is the
duration string itself. A flat `│` with `⏳` or `⏳5m` (still gathering
enough spread to trust a rate) or `∞` (usage genuinely flat — at that pace
it never hits 100%) means no rate signal yet, not "exactly on schedule".
Durations auto-scale (m/h/d). The 7-day window uses its own pacing since
a week moves ~100x slower than 5h: samples hourly (not every 60s), keeps
48h of history (not 20min), needs 2h of real spread (not 3min) before
trusting a rate.

This is all built on Anthropic's **official** `rate_limits.five_hour` /
`seven_day` (`used_percentage`, `resets_at`), captured by the
`statusLine` hook (`--statusline-hook`, requires Claude Code ≥2.1.80) and
cached in `~/.claude/scripts/rate-limits-state.json`. There
is no self-calibrated fallback anymore — official data has proven
reliably available in practice, and a guessed number wasn't worth the
complexity. If the cache is stale (statusLine hasn't fired in 30 min,
e.g. right after enabling, or on an older Claude Code), `--pulse-detail`
says so instead of showing something made up.

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

If both are ✅, this *is* the "tap the icon for detail" flow — run
`python3 SCRIPT --pulse-detail` and show its output as-is, then stop. If
it says there's no data yet (statusLine hasn't fired), say so instead of
running it again.

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

Write back and confirm — end with a one-time pointer to the cheapest
possible "detail" channel there is: this is a live Claude Code session,
so if any icon or number in the status bar is ever unclear, the answer is
always "just ask" — no separate doc lookup needed, and this line only
ever appears once, right here, not on every subsequent status line:
```
✅ oct-pulse 已接上。狀態列會在下一次回覆後出現。
看到不懂的圖示或數字，直接問我就好，不用自己猜。
```

### Disable

Remove the `statusLine` entry only if its command contains
`usage-analyze.py` (never remove someone else's), and remove any
`hooks.Stop` entry containing `--watch`. Plugin-registered hooks can't be
removed here — say so if that's the only one. Confirm:
```
✅ oct-pulse 已關閉。
```
