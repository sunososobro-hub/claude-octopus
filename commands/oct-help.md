# oct-help

Display help for the oct-* toolkit.

## Usage

```bash
/oct-help              # Show all commands
/oct-help wake         # Show help for /oct-wake
/oct-help recall       # Show help for /oct-recall
/oct-help dream        # Show help for /oct-dream
/oct-help sleep        # Show help for /oct-sleep
/oct-help watch        # Show help for /oct-watch
```

## All Commands

**💾 `/oct-save`** — Write a lightweight checkpoint before `/clear`
  - ~1-2k token handoff note: task, key findings, next steps
  - Saved to `~/.claude/summaries/{hash}.md`

**🐙 `/oct-wake`** — One-shot handoff: resume from a checkpoint, not `claude --resume`
  - Loads the latest (or a chosen) checkpoint instead of the whole old session
  - Lists related memory files to optionally load — never auto-loads them
  - Marks the checkpoint consumed so the SessionStart nudge stops repeating

**🧠 `/oct-recall`** — Category-based browsing into curated long-term memory
  - Shows categories from `MEMORY.md`, drill down, or search by keyword
  - Only loads files you explicitly pick — never bulk-loads

**🌙 `/oct-dream`** — Consolidate and organize memories after a work session
  - Detect duplicates/patterns, suggest merges and archiving

**😴 `/oct-sleep`** — End-of-day wrap-up
  - Finalize work, update memory files, archive the session

**📈 `/oct-watch`** — Per-response cost breakdown + rate-limit status
  - Stop hook: prints that response's token/cost breakdown
  - statusLine hook: persistent bottom bar with model, ctx%, and official
    5h/7d rate-limit `reset:X / 可撐:Y`
  - Only command in this list with real enable/disable state:
    `/oct-watch enable` / `/oct-watch disable`

**📊 `/oct-usage`** — Per-session token/cost report (on demand, not automatic)

**❓ `/oct-help`** — This help (you are here)

## Typical Workflow

```
/oct-save            before /clear, or before closing the terminal
  ↓
[new session, later]
/oct-wake             load the checkpoint back — not claude --resume
  ↓
/oct-recall           pull in specific long-term memory if needed
  ↓
... work ...
  ↓
/oct-dream            (periodically) consolidate memory
/oct-sleep            (end of day) finalize and archive
```
