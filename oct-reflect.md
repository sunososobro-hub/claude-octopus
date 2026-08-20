# oct-reflect

Review token usage and cost analysis across sessions.

Reflects on spending to learn patterns and optimize.

## Usage

```bash
/oct-reflect              # Show all-time token summary
/oct-reflect --help       # Show help
/oct-reflect week         # This week's summary
/oct-reflect month        # This month's summary
/oct-reflect task SYS-1859 # Specific task breakdown
```

## What It Shows

```
🔍 Token Reflection Report

Period: 2026-08-18 to 2026-08-20 (3 days)

📊 Total Usage:
  Input tokens: 45.2k
  Output tokens: 23.5k
  Cache read: 892.3k
  Total cost: $28.43

By Model:
  Fable 5: 300k tokens (60%) — $18
  Sonnet 4.6: 150k tokens (30%) — $6
  Haiku 4.5: 50k tokens (10%) — $0.75

By Task:
  SYS-1859: 250k tokens (50%)
  SYS-1844: 200k tokens (40%)
  Other: 50k tokens (10%)

Efficiency Metrics:
  Avg cost per session: $6.85
  Most expensive model: Fable ($9/session)
  Most efficient: Haiku ($0.75/session)

Recommendations:
  → 40% of work could use Haiku instead (save $7.20)
  → Consider Sonnet for medium tasks
  → Fable usage seems appropriate for RCA
```

## How It Works

Reads `~/.claude/token-log.md` which is populated by:
- `/oct-rest` — records checkpoint token usage
- `/oct-sleep` — records session-end token usage

Each entry captures:
```
- Date/Time
- Task
- Model used
- Input/Output/Cache tokens
- Cost
```

Then `/oct-reflect` aggregates across any time period.

## Integration

Typical workflow:
```
Work session
  ↓
[30-60 min] /oct-rest → record tokens
  ↓
[work done] /oct-sleep → final token count
  ↓
[end of week] /oct-reflect → analyze spending
```

## Tips

- Run weekly to spot patterns
- Compare Fable vs Haiku efficiency
- See which tasks are most expensive
- Optimize model selection based on data
