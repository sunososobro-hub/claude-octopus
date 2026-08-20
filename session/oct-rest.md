# oct-rest

Save current session as a checkpoint for later restoration.

Like taking a break and writing down where you left off.

## Usage

```bash
/oct-rest              # Save session summary
/oct-rest --help       # Show help
/oct-rest help         # Show help
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
# a1b2c3d4 | 2026-08-20 16:45

## Task
Implementing auto-routing system for Claude Octopus

## Key Findings
- User preference: suggestions only, not automatic enforcement
- Settings-based config simpler than hook-based approach
- oct- naming scheme works well for namespace

## Next Steps
1. Test with real session flow
2. Integrate into claude-octopus README
3. Push to GitHub and announce

## Related Memory Files
- feedback_language.md (use 繁體中文)
- feedback_commits.md (no Co-Authored-By)

## Important Context
- New user flow: /oct-wake → install → /oct-focus
- Cost savings: 50-80% possible with smart routing
```

## How to Use

1. Complete a work session
2. Run `/oct-rest` to create summary
3. Next session, use `/oct-recall` to restore and continue
4. Saves ~95% of tokens vs replaying full session

## Cost Comparison

| Method | Tokens | Cost |
|---|---|---|
| Full session replay | 50k–150k | $1.50–4.50 |
| oct-rest summary | 1k–2k | $0.03–0.06 |
| **Savings** | | **97–98%** |
