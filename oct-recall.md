# oct-recall

Load memory files into current session context.

## Usage

```bash
/oct-recall          # List all memories, pick to load
/oct-recall <name>   # Load specific memory by name/keyword
```

## How It Works

Read `~/.claude/projects/-home-alonso/memory/MEMORY.md` and list all entries numbered.

```
🧠 oct-recall — Memories

   1  SYS-1796 OWE APCli PMKID
   2  SYS-1811 mt7993 BTM UAF
   3  SYS-1821 MLO FT Roaming
   4  SYS-1844 iPhone Reconnect
   5  SYS-1859 Site-survey 卡30s
   6  SYS-1764 Cross-band FT
   7  5.1.0 MWS Regression
   8  Investigation Orchestrator SOP
   9  Multi-Agent Cost Patterns
  10  Model Roles
  11  oct-watch Feature
  ...

Which to load? (e.g. "3 8 9" or "all")
```

Wait for user input, then read the selected `.md` files from
`~/.claude/projects/-home-alonso/memory/` and output their full content.

Confirm: `✅ Loaded: SYS-1821, Investigation SOP, Multi-Agent Cost Patterns`

## Notes

- Memories stack — loading multiple at once is fine
- Use before starting complex tasks to prime context
- Session resume → use built-in `claude --resume` picker
