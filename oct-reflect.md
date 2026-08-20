# oct-reflect

Automatically diagnose token waste and suggest optimizations.

Like reflecting after a day's work — find what's wasteful, fix it.

## Usage

```bash
/oct-reflect              # Run full diagnosis
/oct-reflect --help       # Show help
/oct-reflect help         # Show help
```

## What It Does

Automatically scans and diagnoses token waste:

```
🔍 Oct-Reflect: Token Waste Diagnosis

1️⃣ MCP Servers (loaded every session)
   deferred_tools_delta: ~1,912 tokens
   💡 Disable unused: /mcp → disable

2️⃣ Skills (loaded every session)
   12 skills installed: ~4,823 tokens/session
   Largest: oct-dream (684), oct-help (679)
   💡 Remove unused: /oct-forget

3️⃣ Memory Files (loaded on demand)
   ⚠️ sys1859-complete.md: 5,190 words (too large)
   ⚠️ sys1821-complete.md: 2,880 words
   ⚠️ completed bugs still active
   💡 Archive: /oct-dream

4️⃣ Usage Patterns
   56% from subagent-heavy sessions
   42% at >150k context
   15% from Gmail MCP
   💡 Avoid agents for simple tasks

📊 Summary:
   Quick wins: disable MCP, archive bugs, reduce agents
   Estimated savings: ~8,411 tokens/session
```

## How to Run

```bash
~/.claude/scripts/reflect-analyze.sh
```

## Integration

Run after `/oct-sleep` for weekly reflection:

```
Work week
  ↓
/oct-sleep (each day)
  ↓
/oct-reflect (weekly)
  → Find waste
  → Apply fixes
  → Next week costs less
```
