# oct-recall

Browse session history and restore previous work.

## Usage

```bash
/oct-recall [filter]
```

### View History
```bash
/oct-recall              # today + yesterday (default)
/oct-recall yesterday    # yesterday only
/oct-recall -2           # 2 days ago
/oct-recall 5            # last 5 sessions
/oct-recall all          # everything
```

### Restore a Session
```bash
/oct-recall 1    # restore session #1
```

Shows available summaries and lets you pick which to restore.

## How It Works

- Scans `~/.claude/sessions/` for Claude Code session logs
- Shows summaries from `~/.claude/summaries/` (created by `/oct-rest`)
- You select which session to restore
- Claude loads context and you're ready to continue

## Tips

- Use `/oct-rest` after completing a task to save a summary
- Summaries are lightweight (~1-2k tokens)
- Works across machines — summaries are just markdown files
