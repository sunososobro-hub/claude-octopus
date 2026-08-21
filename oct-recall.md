# oct-recall

Browse session history and restore previous work.

## Usage

```bash
/oct-recall              # today + yesterday (default)
/oct-recall yesterday    # yesterday only
/oct-recall -2           # 2 days ago
/oct-recall 5            # last 5 sessions
/oct-recall all          # everything
/oct-recall --help       # Show help
/oct-recall help         # Show help
```

### Restore a Session
Pick from history to restore context and continue work.

## How It Works

- Scans session logs and summaries
- Shows history with task descriptions
- Pick one to restore (lightweight, ~1-2k tokens)
- Ready to continue from where you left off

## Tips

- Use `/oct-rest` after tasks to create summaries
- Summaries work across machines (just markdown files)
- Cheaper than full session replay
