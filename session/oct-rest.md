Generate a session handoff summary and save it for later use with `/load`.

Steps:
1. Run this to get the current session hash:
```bash
PROJ_DIR="$HOME/.claude/projects/$(echo "$HOME" | sed 's|/|-|g')"
ls -t "$PROJ_DIR"/*.jsonl 2>/dev/null | head -1 | xargs basename | cut -c1-8
```

2. Generate a concise summary (under 400 tokens) in this format:

```markdown
# {hash} | {YYYY-MM-DD HH:MM}

## Task
{What was being worked on, 1-2 sentences}

## Key Findings
{Important discoveries or decisions, bullet points}

## Next Steps
{Concrete todos, numbered list}

## Relevant Memory Files
{Memory files related to this task}

## Important Context
{Short-term info the next session needs that isn't in memory files}
```

3. Save to `~/.claude/summaries/{hash}.md` using the Write tool.

4. Confirm: "Saved as `{hash}`. Use `/load` to restore in a future session."
