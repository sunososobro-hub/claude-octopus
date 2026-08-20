# oct-router 🚀

Intelligent task routing: suggests optimal model and agents for your work.

## Philosophy

- **Suggest, don't enforce** — recommendations, not mandates
- **Cost-aware** — always shows potential savings
- **Transparent** — users know why each model was chosen
- **Learning-friendly** — explains routing decisions so you can make better choices

## Features

### 1. Complexity Analysis
Reads your task and estimates:
- Low (simple reads/edits) → Haiku sufficient
- Medium (debugging/reasoning) → Sonnet recommended  
- High (complex RCA/design) → Fable needed

### 2. Cost Calculation
Shows:
- Current model cost for this task
- Recommended model cost
- Potential savings (in $ and %)

### 3. Model Suggestion
```
💡 Optimization Found

Task: "Debug the authentication flow"
Complexity: Medium

Current: Fable 5 (cache read $0.56)
Suggested: Sonnet 4.6 (cache read $0.12)

Savings: $0.44 (79%)

Ready? [Yes] [No] [Learn more]
```

### 4. Agent Routing (future)
Will also suggest:
- Use Explore agent for search-heavy tasks
- Use general-purpose for multi-step analysis
- Batch multiple questions before opening agents

## How to Use

**Manual check:**
```bash
/oct-route
```

**At session start (optional hook):**
- Analyzes first few messages
- Suggests optimizations if found
- You can ignore or accept

**Learning path:**
```bash
/oct-learning
→ Choose "Auto-routing"
→ Install oct-router
```

## Configuration

Edit `~/.claude/settings.json`:
```json
{
  "oct-router": {
    "enabled": true,
    "auto-suggest": true,
    "min-savings-threshold": "30%"
  }
}
```

---

## Implementation Notes

- Complexity detection uses keywords + token count heuristics
- Model selection based on Claude's recommendations
- Hook integration via `~/.claude/hooks/`
- Future: ML-based complexity scoring
