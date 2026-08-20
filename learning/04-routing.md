# Auto-Routing: How the System Chooses for You

## The Idea

Instead of you manually deciding "should I use Haiku or Fable?", the system watches your task and **suggests** the optimal model + cost savings.

You always have the final say.

---

## How It Works

### Step 1: Analyze Your Input

When you type a message, the system checks:

```
✓ Task complexity
  - Keywords: "debug", "trace", "investigate" → medium/high
  - Keywords: "read", "explain", "format" → low
  - Code involved? Single file or multiple?
  
✓ Current model
  - What are you using now? (Fable/Sonnet/Haiku)
  
✓ Context size
  - Big context = cache will be read anyway (model choice matters less)
  
✓ Requires agents?
  - "search", "grep", "find" in your task? → Explore agent
  - Multiple perspectives needed? → general-purpose agent
```

### Step 2: Calculate Potential Savings

```
Current: Fable 5 cache read on 365k tokens = $0.56
Suggested: Haiku cache read on same 365k tokens = $0.05
Savings: $0.51 (91%)
```

### Step 3: Make Suggestion (Not Enforce)

The system offers:

```
💡 Optimization Available
   Task: "Explain how the code works"
   Complexity: Low
   
   Current model: Fable 5
   Suggested model: Haiku 4.5
   
   Estimated savings: 91% ($0.56 → $0.05)
   
   Ready? [Yes, use Haiku] [No, keep Fable] [Show details]
```

You decide. Sometimes you want Fable for peace of mind; that's valid.

---

## Complexity Scoring

The system uses this heuristic (not perfect, but pragmatic):

### Low Complexity (~20 tokens to decide)
- "Read this file and explain"
- "Fix the typo"
- "Format this JSON"
- "What does this line do?"
- **→ Haiku suffices**

### Medium Complexity (~500 tokens to decide)
- "Why is this slow?"
- "Debug this error"
- "Find where this is called"
- "Should we refactor this?"
- **→ Sonnet recommended**

### High Complexity (~5k+ tokens to decide)
- "Debug this intermittent race condition"
- "Design a new API"
- "What's the root cause of the crash?"
- **→ Fable recommended**

---

## Example Scenarios

### Scenario 1: Quick Code Read
```
You: "Can you explain what this function does?"
File: 20 lines, simple logic

System: Haiku is plenty. Suggest Haiku.
Savings: -85%
```

### Scenario 2: Multi-File Bug
```
You: "Why is the authentication failing?"
Context: 5 files involved, timer logic, edge cases

System: Sonnet strikes the balance.
Savings: -50%
```

### Scenario 3: Strange Intermittent Crash
```
You: "We've tried everything. Help us RCA this."
Context: Logs, multiple subsystems, timing dependent

System: Fable is worth it. No suggestion needed.
Savings: 0% (already optimal)
```

---

## Rules of Thumb

✓ **If the system suggests Haiku, try it** — you can always re-run with Sonnet/Fable  
✓ **If you're unsure, default to Sonnet** — middle-ground choice  
✓ **Only use Fable when thinking is hard** — novel problems, complex reasoning  
✓ **Cache makes model choice even more important** — switching from Fable to Haiku saves more when cache is large  

---

## What if It Gets It Wrong?

The system isn't perfect. If Haiku struggles:

1. You reject the suggestion → keeps using Fable
2. Run again with Sonnet or Fable
3. System learns and adjusts its scoring

This is why it's a suggestion, not a mandate.

---

## Next: Installation & Setup

Ready to enable auto-routing? Run `/oct-learning install` to set up the hook.
