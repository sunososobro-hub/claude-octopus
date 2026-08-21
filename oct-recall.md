# oct-recall

Browse session history and memory files. Load selected context into current session.

## Usage

```bash
/oct-recall          # Show sessions + memory list
/oct-recall <id>     # Load a specific session's context
```

## What It Shows

Two sections:

### 📋 Sessions
Run: `python3 ~/.claude/scripts/usage-analyze.py --recall`

Shows last 10 sessions with description. User picks one to preview context (read first few user messages + last assistant summary from the session JSONL).

### 🧠 Memories
Read `~/.claude/projects/-home-alonso/memory/MEMORY.md` and list all entries with their one-line descriptions, numbered.

User selects one or more (e.g. "1 3 5" or "SYS-1821 and SOP"). Read those memory files and output their content into the current context.

## Example Output

```
📋 Sessions (last 10)

  7d5eb4e3  2026-08-21  oct-watch、multi-agent 架構、記憶整理
  fd957762  2026-08-21  oct-watch 開發、/clear API
  d76c8f77  2026-08-21  oct-usage 開發、token usage 功能

  Resume: claude --resume <id>
  Load context here: /oct-recall <id>

🧠 Memories

   1  SYS-1796 OWE APCli PMKID
   2  SYS-1811 mt7993 BTM UAF
   3  SYS-1821 MLO FT Roaming
   4  SYS-1844 iPhone Reconnect
   5  SYS-1859 Site-survey 卡30s
   6  Investigation Orchestrator SOP
   7  Multi-Agent Cost Patterns
   8  Model Roles
  ...

Which memories to load? (e.g. "3 6 7" or Enter to skip)
```

## Loading Session Context

When user picks a session ID, read the session JSONL:
`~/.claude/projects/-home-alonso/<full-id>.jsonl`

Extract and summarize:
- First 3 user messages (what was the task)
- Last 3 assistant messages (what was concluded)
- Any files modified (tool calls with Edit/Write)

Present as compact context block (~300 words max).

## Loading Memories

When user selects memory numbers or names:
- Read each .md file from `~/.claude/projects/-home-alonso/memory/`
- Output full content of selected files
- Confirm: `✅ Loaded: SYS-1821, Investigation SOP, Multi-Agent Cost Patterns`

Memories stack — loading multiple is fine and encouraged before starting complex tasks.
