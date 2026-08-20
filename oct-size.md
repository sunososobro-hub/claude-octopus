# oct-size

Check current session context size quickly.

## Usage

```bash
/oct-size              # Show current session size
/oct-size --help       # Show help
/oct-size help         # Show help
```

## What It Shows

```
📊 Current Session Size

File size: 145K
Estimated tokens: ~650-750
Context usage: ██████░░░░░░░░░░░░░ 32%

Status: ✅ Healthy
└─ Lots of room left, work freely
```

## How It Works

1. Finds current session file in `~/.claude/projects/`
2. Gets file size
3. Estimates tokens (rough: 1 MB ≈ 5k tokens)
4. Calculates % of typical context window (128k-200k tokens)
5. Shows status and recommendations

## Size Reference

```
< 50K    — Very small (< 5%)
50-200K  — Small (5-20%)
200-500K — Medium (20-50%)
500K-1M  — Large (50-80%)
> 1M     — Very large (> 80%) ⚠️
```

## Tips

- Run `/oct-size` regularly to track growth
- If growing fast, consider `/oct-rest` soon
- Combine with `/oct-monitor` for automatic alerts
