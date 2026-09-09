# oct-toolkit

Token-frugal session memory and usage tracking for Claude Code.

## Why

`claude --resume` reattaches a whole old session — every message, every file
read, still sitting in context on every future turn. This toolkit's core bet
is that **curated, selective recall beats automatic full-context reload**:
save a small handoff note, start clean, load only what's actually relevant.

This is a deliberate contrast to auto-capture-everything memory tools. Those
are convenient, but real users report they can *increase* token usage (the
compression/injection steps aren't free, and automatic relevance-guessing
over-injects). Nothing here loads automatically except a one-line "you have
a pending checkpoint" nudge — everything else is loaded on request.

## What's in it

- **`/oct-nap`** — write a ~1-2k token checkpoint before `/clear`
- **`/oct-wake`** — load the latest checkpoint (not the whole old session) in
  one shot; `/oct-wake <keyword>` also searches curated long-term memory
- **`/oct-dream`** / **`/oct-sleep`** — periodic memory consolidation
- **`/oct-pulse`** — per-response token/cost breakdown (Stop hook), plus a
  persistent status-bar line with Anthropic's *official* 5h/7d rate-limit %
  and a reset-vs-ETA comparison so you can tell at a glance whether you'll
  hit the cap before the window resets on its own
- **`/oct-checkup`** — per-call token/cost table for a session;
  `/oct-checkup habits` scans the last N days of transcripts for spending
  patterns (long answer → immediate short question, chatter on a fat
  context, repeated corrections, fat session ended without a checkpoint)
  and proposes one-line memory rules — you pick which to save
- **Read-dedup hook** — blocks a byte-identical re-read of a file already
  read this session (same path, mtime, size, offset/limit), so duplicate
  content doesn't double up in context

## Typical day

```
/oct-wake             morning — load yesterday's note, not the whole old session
  ↓
... work ...          ctx% creeping up, or stepping away?  →  /oct-nap, then /clear
  ↓
/oct-wake <keyword>   "didn't I hit this before?" — search notes + long-term memory
  ↓
/oct-sleep            end of day — note + memory consolidation in one shot
                      (weekly, or after a big task: /oct-dream on its own)
```

## Install

```bash
git clone <this-repo> ~/.claude/skills/oct-toolkit
```

(Not `~/.claude/plugins/` — a bare clone there is never auto-discovered.
`~/.claude/skills/<name>/.claude-plugin/plugin.json` is what Claude Code
picks up on its own, no marketplace or install step needed.)

Then open Claude Code. You'll see one line:

```
🐙 oct-toolkit 已安裝。底部狀態列還沒開——輸入 /oct-pulse 一鍵開啟。
```

Type `/oct-pulse`, answer yes, done. That's the whole setup.

<details>
<summary>Why that one step is manual, and what it writes</summary>

Commands and hooks (`SessionStart`, `PreToolUse[Read]`, `Stop`) load
automatically with the plugin. The bottom status bar is different: it's a
single `statusLine` setting in `~/.claude/settings.json`, and a plugin
shouldn't silently take it over — you might already be using it for
something else. So `/oct-pulse` asks first, then writes:

```json
"statusLine": {
  "type": "command",
  "command": "python3 ~/.claude/skills/oct-toolkit/scripts/usage-analyze.py --statusline-hook"
}
```

Without it, the per-response cost line still works; the 5h/7d quota
numbers (which come from Anthropic's official `rate_limits`, delivered
only through the statusLine payload) won't appear.

If your Claude Code prefers marketplace installs, add this repo as a
marketplace source and install `oct-toolkit` from it — same result.
</details>

## Requirements

- Claude Code ≥2.1.80 for official `rate_limits` (older versions fall back
  automatically)
- Python 3

## License

MIT
