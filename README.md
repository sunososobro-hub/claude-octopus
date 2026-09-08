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

- **`/oct-save`** — write a ~1-2k token checkpoint before `/clear`
- **`/oct-wake`** — load the latest checkpoint (not the whole old session) in one shot
- **`/oct-recall`** — category-based browsing into curated long-term memory files
- **`/oct-dream`** / **`/oct-sleep`** — periodic memory consolidation
- **`/oct-watch`** — per-response token/cost breakdown (Stop hook), plus a
  persistent status-bar line with Anthropic's *official* 5h/7d rate-limit %
  and a reset-vs-ETA comparison so you can tell at a glance whether you'll
  hit the cap before the window resets on its own
- **Read-dedup hook** — blocks a byte-identical re-read of a file already
  read this session (same path, mtime, size, offset/limit), so duplicate
  content doesn't double up in context

## Install

Clone this repo into your plugins directory:

```bash
git clone <this-repo> ~/.claude/plugins/oct-toolkit
```

Claude Code should pick up the plugin's commands and hooks (`SessionStart`,
`PreToolUse[Read]`, `Stop`) automatically. If your Claude Code version
prefers marketplace-based install instead, add this repo as a marketplace
source and install `oct-toolkit` from it the same way.

**One manual step**: the `--watch` ETA line is most accurate when it can
read Anthropic's real rate-limit data, which requires a `statusLine` hook.
Plugins shouldn't silently claim your terminal's status bar (it's a
singleton setting), so wire this yourself in `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 ~/.claude/plugins/oct-toolkit/scripts/usage-analyze.py --statusline-hook"
}
```

It prints a status line (model, context %, 5h/7d reset+ETA) — Claude Code
reserves that bottom row whenever any `statusLine` hook is configured at
all, so there's no point leaving it blank. Without this step, `/oct-watch`
still works, just with a less accurate self-calibrated estimate instead of
official numbers.

## Requirements

- Claude Code ≥2.1.80 for official `rate_limits` (older versions fall back
  automatically)
- Python 3

## License

MIT
