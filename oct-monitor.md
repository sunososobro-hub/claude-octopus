# oct-monitor

Smart background monitoring for context bloat prevention.

Automatically detects when you should take a break and start fresh.

## Usage

```bash
/oct-monitor              # Show monitoring status
/oct-monitor --help       # Show help
/oct-monitor enable       # Enable monitoring
/oct-monitor disable      # Disable monitoring
/oct-monitor status       # Show current context usage
```

## How It Works

Monitors context growth intelligently:

```
📊 Normal (< 70%): No action
   Every 30 min: Quick check (~0 cost, cached)

⚠️  Warning (70-85%): Heads up
   Every 15 min: Check
   Alert once: "Context growing. Consider /oct-rest soon"

🔴 Critical (> 85%): Act now
   Every 10 min: Check  
   Alert once: "Context full! Do /oct-rest + new agent"

After /oct-rest or new agent:
   Counters reset, ready to monitor again
```

## Configuration

In `~/.claude/settings.json`:

```json
{
  "oct-monitor": {
    "enabled": true,
    "mode": "smart",
    "check-interval": {
      "normal": 1800,    // 30 min
      "warning": 900,    // 15 min at 70%+
      "critical": 600    // 10 min at 85%+
    },
    "thresholds": {
      "warning": 70,
      "critical": 85
    },
    "alert-once": true,
    "cost-estimate": "NT$5-15/月 (smart checks only)"
  }
}
```

## Cost Breakdown

- Idle session: $0/month
- Normal work (30-min checks): ~$2-5/month  
- Active work (15-min checks): ~$10-15/month
- **Total: NT$5-15/month on average**

## Disable Anytime

```bash
/oct-monitor disable
```

Re-enable with:
```bash
/oct-monitor enable
```
