# oct-save

Save current session state as a checkpoint before clearing context.

## Usage

```bash
/oct-save              # Save session summary
```

## What It Does

Creates a lightweight handoff note (~1-2k tokens) that captures:
- What you were working on
- Key findings and decisions
- Next steps
- Related memory files
- Short-term context

Saves to `~/.claude/summaries/{hash}.md` for use with `/oct-recall`.

## Format

```markdown
# a1b2c3d4 | 2026-08-21 16:45

## Task
[what the user was working on]

## Key Findings
- [important discoveries or decisions]

## Next Steps
1. [what to do next]

## Related Memory Files
- [relevant memory files]

## Important Context
- [anything that would be lost after /clear]
```

## Instructions

1. Generate the summary in the format above.
2. Save it to `~/.claude/summaries/{8-char-hash}.md` using the Write tool.
3. Output only:

```
✅ ~/.claude/summaries/{hash}.md
```

Do NOT print the summary content.
