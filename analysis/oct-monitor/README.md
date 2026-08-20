# oct-monitor 📊

Smart background context monitoring system.

## Purpose

Automatically detects when your session is bloating and suggests a graceful handoff:
- Save checkpoint with `/oct-rest`
- Start fresh with a new agent
- Restore context with `/oct-recall`

## How It Works

### Check Intervals (Smart)

```
Context < 70%: Every 30 min (light monitoring)
Context 70-85%: Every 15 min (closer watch)
Context > 85%: Every 10 min (urgent watch)

Idle sessions: No monitoring (saves cost)
```

### Alerts (One-Time)

```
⚠️  Context 70-85%
    Alert once: "Consider /oct-rest soon"
    
🔴 Context > 85%
    Alert once: "Context full. Do /oct-rest + new agent"

After /oct-rest or new agent:
    Alert counters reset
```

### Cost Optimization

- Smart checks use cached context (minimal cost)
- Only active sessions monitored
- Average: NT$5-15/month

## Configuration

```json
{
  "oct-monitor": {
    "enabled": true,
    "mode": "smart",
    "check-interval": {
      "normal": 1800,    // 30 min
      "warning": 900,    // 15 min
      "critical": 600    // 10 min
    },
    "thresholds": {
      "warning": 70,
      "critical": 85
    },
    "alert-once": true
  }
}
```

## Implementation

Runs as:
1. Hook: Triggered by message send or periodic check
2. Analyzes current context size
3. Compares against thresholds
4. Shows alert (one-time per session)
5. Suggests `/oct-rest` → new agent → `/oct-recall`

## Disable

```bash
/oct-monitor disable
```

## Future Improvements

- Predict context growth rate ("at current rate, will hit limit in 2 hours")
- Auto-trigger `/oct-rest` (with permission)
- Integration with agent spawning (auto-handoff)
