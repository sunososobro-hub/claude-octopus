# Why Your Token Costs Are High (And How to Fix It)

## The Problem

You just opened a new Claude Code session to ask a simple question. Five minutes later: **$0.71**.

That seems expensive for a casual chat, right?

## What Actually Happened

Your session had:
- **5.1k input tokens** (Fable) + **1.3k input tokens** (Haiku) = ~6.4k new tokens generated
- **365k tokens read from cache** (system prompts, MEMORY, MCP definitions)

### The Cost Breakdown

| | Price | Your Session | Impact |
|---|---|---|---|
| New token generation | $0.30 / 1M (Fable) | 5.1k | $0.0015 |
| Cache read | $0.03 / 1M (Fable) | 163k | $0.0049 |
| New token generation | $0.015 / 1M (Haiku) | 1.3k | $0.00002 |
| Cache read | $0.0015 / 1M (Haiku) | 201k | $0.0003 |
| **Total** | | | **$0.71** |

**The real culprit: using Fable 5 for cache reads that Haiku could have handled.**

## The Solution: Right-Sizing Your Model

Same conversation, optimized:
- Use **Haiku for cache reads** (simple context) → $0.05 instead of $0.56
- Use **Fable only for complex reasoning**
- Total cost drops to **$0.20** — 72% savings

## Key Insight

Cache is cheap (1/10 the price of new tokens). But **choosing the wrong model for cache-heavy work is expensive**.

## What You'll Learn Next

→ Part 3: Model Selection Guide — when to use Haiku, Sonnet, Fable
