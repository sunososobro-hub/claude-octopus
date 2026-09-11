---
description: Second opinion — dispatch a clean cold sub-agent with a neutral brief to decide; no model switch, no clearing. `--here` re-evaluates in the current model instead.
---

# oct-consult

**Will this take 3+ more turns with the bigger model?** Yes → `/model <higher-tier>` then run `/oct-consult --here`. No (the common case) → just run it, Mode A.

`$ARGUMENTS`:
- empty → Mode A, about whatever decision was discussed most recently
- `<keyword>` → Mode A, about the decision that keyword points to
- `--here` → Mode B, re-evaluate in the current model (can combine with a keyword)

## Mode A (default): cold sub-agent

You (the resident model) don't switch model or clear the conversation — instead you dispatch a clean sub-agent to decide.

1. Write a **neutral brief**. No recommendation, no leaning:
   ```
   ## Question (one line)
   ## Facts (bulleted, with file paths/line numbers so the agent can verify)
   ## Options (a1/a2/a3…, one line each, unordered)
   ## Constraints (any hard constraints already agreed on — priorities, cost rules, etc.)
   ## What to return (list what you'd push back on first, then a conclusion + one-line reason; ≤300 words)
   ```
   End the brief with: **read the files listed above before deciding; if the brief and the files disagree, the files win — say so.**
2. Call `Agent(subagent_type: "general-purpose", model: "fable", description: "cold decision: <topic>", prompt: brief)`.
   If that model isn't available on your plan, retry once with `model: "opus"` — don't fall back further than that.
   Don't use a fork (a fork always runs on the parent model and carries the whole conversation). Don't run it in the background — a decision is something you wait for.
3. When the reply comes back, relay only the **conclusion and the objections it raised** — don't reprint the brief.
4. If several decisions have piled up, put them all in one brief and spawn once.

## Mode B (`--here`): re-evaluate in the current model

Don't assume the conclusion already reached in this conversation is right — re-evaluate it yourself: list the objections you'd otherwise raise first, then give your own conclusion.

Use this only when:
- You're about to work with the bigger model for **3+ more turns** (design, distillation, writing a handoff)
- The decision depends on **context that only exists in this conversation** — writing it into a brief would lose something real

## What this is, and isn't

Three ways to get a better second opinion, trading off cost against how independent the judgment actually is:

1. **Just switching model** (`/model opus` without saying anything): the new model sees the entire prior discussion and hasn't been told to question it — easiest to get anchored on whatever framing came before. Cache is model-bound too, so the new model re-reads the whole history — the longer the conversation, the pricier that ticket.
2. **Mode B (`--here`)**: use right after switching model. **Keeps full memory** but explicitly says not to assume the earlier conclusion was right. This is **independence at a discount** — it still sees how the discussion was framed.
3. **New session, neutral write-up**: the new model only ever sees the facts you deliberately wrote down — genuine independence, at the cost of writing that summary yourself. **Mode A is the automated version of this tier**: the resident model writes the brief and spawns the cold agent for you, so you don't write anything and don't have to clear the conversation. The sub-agent only reads one page, so the ticket price is fixed and doesn't grow with how long your conversation already is.
