# oct-wake

Bootstrap Claude Octopus and install cost optimization tools.

## Quick Help

```bash
/oct-wake              # Start setup wizard
/oct-wake --help       # Show this help
/oct-wake help         # Show this help
```

## What It Does

First-time setup: detects high token usage and offers to install auto-routing.

```
🐙 Claude Octopus — Cost Optimization

Detected: You're using expensive models for routine tasks
Opportunity: Save 50-80% with smart model selection

Want to set up auto-routing? It will:
✓ Analyze task complexity (Low/Medium/High)
✓ Suggest optimal model (Haiku/Sonnet/Fable)
✓ Show cost savings ($X saved)
✓ Let YOU decide (suggestions only, not automatic)

Install now? [Yes] [No] [Learn more]
```

## What Happens

If Yes:
1. Write config to `~/.claude/settings.json`
2. Enable auto-routing hook
3. Install `/oct-focus` command
4. Ready immediately (no restart needed)

If No:
- Remember for later when savings are large

If Learn more:
- Show course files: why costs are high, model selection, how routing works

## Available After Setup

- `/oct-focus` — get model suggestions for current task
- `/oct-dream` — consolidate and organize your memories
- `/oct-rest` — save current session
- `/oct-recall` — restore previous sessions
- `/oct-forget` — remove tools anytime
