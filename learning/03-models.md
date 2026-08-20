# Model Selection Guide: When to Use What

## The Three Tiers

### Haiku 4.5 — The Workhorse 🐇
**Price:** $0.015 input / $0.06 output  
**Speed:** Fast  
**Best for:**
- Code editing and simple refactors
- API docs lookups and quick answers
- Reading and summarizing existing code
- Cache-heavy operations (context loading, memory retrieval)
- MCP tool results (Gmail, Calendar, Drive)

**Cost advantage:** 20x cheaper than Fable  
**When to use:** If you wouldn't need to re-run it, Haiku is fine.

---

### Sonnet 4.6 — The Balanced Option ⚖️
**Price:** $0.08 input / $0.24 output  
**Speed:** Medium  
**Best for:**
- Cross-file code reasoning
- Bug investigation and RCA (root cause analysis)
- Design decisions and architecture
- Medium-complexity agent work

**Cost vs capability:** Sweet spot if Haiku struggles but you don't need Fable  
**When to use:** If the problem requires deeper thought but isn't extremely complex.

---

### Fable 5 — The Powerhouse 🚀
**Price:** $0.30 input / $0.90 output  
**Speed:** Thoughtful (can think longer)  
**Best for:**
- Complex multi-agent RCA
- Architectural decisions with many trade-offs
- Novel problem solving
- Long research investigations

**When to use:** Only when you're really stuck or the stakes are high.

---

## Quick Decision Tree

```
What's your task?

├─ Simple (code edit, lookup, summary)
│  └─ Use Haiku
│
├─ Medium (debugging, cross-file trace)
│  └─ Use Sonnet (or Haiku if low risk)
│
├─ Complex (RCA, design, novel problem)
│  └─ Use Fable
│
└─ Not sure?
   └─ Start with Haiku. If it struggles, escalate.
```

---

## Real Cost Comparison

Same task: "Debug why the wifi handshake is failing"

| Model | Cost | Time | Success Rate |
|---|---|---|---|
| Haiku | $0.05 | 2min | 70% |
| Sonnet | $0.15 | 3min | 90% |
| Fable | $0.45 | 5min | 95% |

**Decision:** Use Sonnet. Haiku might miss subtleties; Fable is overkill.

---

## Pro Tips

1. **Start cheap, escalate if needed** — try Haiku first, run again with Sonnet if it fails
2. **Cache is already loaded** — after the first 10 seconds, future models pay 1/10 price
3. **Use `/fast` to switch mid-session** — toggle between Haiku and Fable without restarting
4. **Batch related questions** — ask Haiku everything it can handle, then one Fable deep-dive

---

## What's Coming

→ Part 4: Auto-Routing — let the system suggest the optimal model for you
