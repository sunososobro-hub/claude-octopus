# claude-octopus 🐙

> Claude Code commands for session continuity and workflow management.
> Like an octopus — multiple arms working in parallel, coordinated by one brain.

## The Problem

Long Claude Code sessions get expensive. Reboots, context limits, and tab switches break your flow. You end up re-explaining everything from scratch.

## The Solution

Three commands that let you save where you left off and pick it back up — with minimal token cost.

## Commands

### `/oct-summary`
Save the current session as a compact handoff note (~400 tokens).

```
/oct-summary
→ Saved as a1b2c3d4. Use /oct-load to restore in a future session.
```

### `/oct-load`
Browse and restore previous sessions.

```
/oct-load
→ Available summaries (last 5):
    1. a1b2c3d4 | 2026-08-20 16:00  —  Debugging MT7927 wifi driver
    2. e5f6a7b8 | 2026-08-19 22:30  —  SYS-1859 scan fix verification
  Which to load? 
```

### `/oct-sessions [filter]`
Browse your Claude Code session history.

```
/oct-sessions           # today + yesterday (default)
/oct-sessions yesterday # yesterday only
/oct-sessions -2        # 2 days ago
/oct-sessions 5         # last 5 sessions
/oct-sessions all       # everything
```

## Install

```bash
git clone https://github.com/your-username/claude-octopus
cd claude-octopus
./install.sh
```

That's it. No runtime, no database, no background process.

## How It Works

- `/oct-summary` writes a markdown file to `~/.claude/summaries/{hash}.md`
- `/oct-load` reads those files and restores context on demand
- `/oct-sessions` parses Claude Code's own `.jsonl` session logs

Everything is plain markdown. You can read, edit, or delete any file directly.

## Roadmap

- `session/` — session continuity tools ✅
- `report/` — generate structured reports from conversations
- `analysis/` — multi-agent problem analysis and RCA

## License

MIT
