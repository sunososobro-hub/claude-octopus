# oct-focus

Analyze current task and suggest optimal model.

Like pausing to think clearly before acting.

## Usage

```bash
/oct-focus              # Analyze task & suggest model
/oct-focus --help       # Show help
/oct-focus help         # Show help
```

Shows:
```
🤖 Task Complexity Analysis

Your recent input: "Debug why the WiFi handshake is failing"

Complexity: MEDIUM
├─ Keywords detected: debug, failing (⚠ requires reasoning)
├─ Code files involved: Yes, multiple (⚠ cross-file trace)
└─ Context size: 250k tokens (note: cache read is bulk cost)

Current model: Fable 5 ($0.30/1M input)
Recommended: Sonnet 4.6 ($0.08/1M input)

Savings available: $0.18 (60%)

Ready to switch? [Yes, use Sonnet] [No, keep Fable] [Explain]
```

## How It Works

1. **Analyzes your input** for complexity signals:
   - Keywords: "debug", "trace", "design" → higher complexity
   - Code involved? Single vs multiple files
   - Context size (indicates how much cache will be read)

2. **Estimates task difficulty**:
   - Low: reads, explanations, formatting → Haiku
   - Medium: debugging, cross-file analysis → Sonnet  
   - High: RCA, design, novel problems → Fable

3. **Calculates potential savings**:
   - Based on current model vs recommended
   - Shows both % and $ savings

4. **Asks for permission** — you decide whether to switch

## Examples

### Example 1: Simple Read
```
Your task: "Explain this function"
Complexity: LOW

Current: Fable 5 (overkill)
Suggested: Haiku 4.5

Savings: $0.56 → $0.05 (91%)
```

### Example 2: Medium Debugging
```
Your task: "Why is auth timing out?"
Complexity: MEDIUM

Current: Fable 5 (unnecessary)
Suggested: Sonnet 4.6 (better value)

Savings: $0.30 → $0.08 (73%)
```

### Example 3: Complex RCA
```
Your task: "Debug this race condition"
Complexity: HIGH

Current: Fable 5 (correct choice)
No suggestion needed — Fable is optimal
```

## Implementation

When invoked, this skill:
1. Reads recent conversation history
2. Sends to Claude for complexity analysis
3. Compares current model vs optimal
4. Displays recommendation with savings
5. Executes user's choice (if any)

Future: Will integrate with hooks for automatic suggestions.
