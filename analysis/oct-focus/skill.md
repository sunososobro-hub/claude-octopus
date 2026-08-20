# oct-focus

Analyze current task and suggest optimal model.

Like pausing to think clearly before acting.

## Usage

```bash
/oct-focus
```

## What It Does

Analyzes your recent work and suggests the best model:

```
🧠 Task Focus Analysis

Your task: "Debug why the WiFi handshake is failing"

Complexity: MEDIUM
├─ Keywords: debug, failing (requires reasoning)
├─ Code involved: multiple files (cross-file trace)
└─ Context: 250k tokens

Current model: Fable 5 ($0.30/1M)
Recommended: Sonnet 4.6 ($0.08/1M)

Savings: $0.18 (60%)

Ready to switch? [Yes] [No] [Explain]
```

## How It Works

Analyzes:
1. Keywords in your task
2. How many files involved
3. Context size
4. Current vs optimal model

Then calculates potential savings and asks permission.

## Examples

- Simple read → Haiku (91% savings)
- Medium debugging → Sonnet (73% savings)
- Complex RCA → Fable (no suggestion needed)
