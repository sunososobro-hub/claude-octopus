# oct-wake

Bootstrap Claude Octopus and install cost optimization tools.

First-time setup for new users.

## Usage

```bash
/oct-wake
```

## What It Does

Detects high token usage and offers to install auto-routing:

```
🐙 Claude Octopus — Cost Optimization

You're using expensive models for routine tasks.
Save 50-80% with smart model selection!

Want auto-routing? It will:
✓ Analyze task complexity (Low/Medium/High)
✓ Suggest optimal model (Haiku/Sonnet/Fable)
✓ Show cost savings ($X saved)
✓ Let you decide (user-controlled)

Install now? [Yes] [No] [Learn more]
```

## Installation

If Yes:
1. Writes config to `~/.claude/settings.json`
2. Enables auto-routing hook
3. Installs `/oct-focus` command
4. Ready immediately

If No:
- Remembers for later

If Learn more:
- Shows course materials

## After Setup

You'll have access to:
- `/oct-focus` — model suggestions
- `/oct-dream` — memory consolidation
- `/oct-rest` — save sessions
- `/oct-recall` — restore sessions
