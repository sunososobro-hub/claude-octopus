# oct-help

Display help for Claude Octopus tools.

## Usage

```bash
/oct-help              # Show all commands
/oct-help wake         # Show help for /oct-wake
/oct-help focus        # Show help for /oct-focus
/oct-help dream        # Show help for /oct-dream
/oct-help rest         # Show help for /oct-rest
/oct-help recall       # Show help for /oct-recall
/oct-help forget       # Show help for /oct-forget
```

Or use individual command help:
```bash
/oct-wake --help
/oct-focus --help
/oct-dream --help
/oct-rest --help
/oct-recall --help
/oct-forget --help
/oct-monitor --help
/oct-size --help
```

## All Commands

**🌅 /oct-wake** — Bootstrap & install cost optimization
  - First-time setup
  - Install auto-routing
  - Enable all tools

**🧠 /oct-focus** — Analyze task & suggest model
  - Evaluate complexity
  - Show cost savings
  - Suggest best model

**🌙 /oct-dream** — Consolidate memories
  - Organize memory files
  - Detect duplicates
  - Archive completed items

**😴 /oct-rest** — Save session checkpoint
  - Create handoff summary
  - Capture findings
  - Prepare for next session

**🔙 /oct-recall** — Restore previous session
  - Browse history
  - Pick session to restore
  - Continue where you left off

**🗑️ /oct-forget** — Uninstall tools
  - Remove selected commands
  - Clear configuration
  - Can reinstall anytime

**📊 /oct-monitor** — Smart background monitoring
  - Detect context bloat automatically
  - Alert when approaching limit (one-time)
  - Cost: ~NT$5-15/month

**📈 /oct-size** — Quick context checker
  - Show current session size
  - Estimate token usage
  - Display health status

**😴 /oct-sleep** — End-of-day wrap-up (NEW)
  - Finalize work session
  - Create final summary
  - Update memory files
  - Archive & prepare for tomorrow

**❓ /oct-help** — This help (you are here)
  - View all commands
  - Get help for specific command

### Complete Daily Workflow

```
🌅 /oct-wake        Morning: Bootstrap
   ↓
🧠 /oct-focus       Analyze task & suggest model
💾 /oct-rest        [30-60 min] Checkpoint
  └─ 📊 Record tokens
   ↓
🌙 /oct-dream       Evening: Organize memory
😴 /oct-sleep       Night: Finalize & summarize
  └─ 📊 Record final tokens
   ↓
🔍 /oct-reflect     Weekly: Analyze spending (NEW)
   ↓
🔙 /oct-recall      Next day: Resume from checkpoint
```

### Token Tracking

**Automatic recording at:**
- `/oct-rest` — Checkpoint tokens (mid-work)
- `/oct-sleep` — Session-end tokens (work complete)

**Analysis:**
- `/oct-reflect` — Aggregate spending patterns
- `/oct-reflect week` — This week's summary
- `/oct-reflect task SYS-1859` — Specific task costs
