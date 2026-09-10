---
description: 深思：切完模型後用，提醒不要預設前面談的結論是對的，自己重新評估
---

# oct-deepthink

Don't assume the conclusion we already reached in this conversation is
right — re-evaluate this decision yourself: first list the objections/
doubts you'd otherwise have raised, then give your own conclusion.

## What this is, and isn't

Three ways to get a better second opinion, trading off cost against how
independent the judgment actually is:

1. **Just switching model** (`/model opus` without this prompt): the new
   model sees the entire prior discussion and hasn't been told to
   question it — easiest to get anchored on whatever framing came before.
2. **`/oct-deepthink` (this command, a hybrid)**: run it right after
   switching model. **Keeps full memory** — all the prior context and
   detail is still there, nothing to re-explain — but explicitly tells it
   not to assume the earlier conclusion was right, pushing it to look
   again from a fresh angle. This is **independence at a discount**, not
   a from-scratch judgment — it still sees how the discussion was framed
   and what got emphasized.
3. **A new session with an objective write-up**: the new model never
   sees the prior recommendation or tone at all, only the neutral facts
   you deliberately wrote down. This is genuine independence, at the cost
   of writing that neutral summary yourself — none of the original
   context carries over automatically.

Use `/oct-deepthink` for a quick "don't just rubber-stamp what we already
said" check mid-conversation. Save option 3 for decisions important
enough to be worth that cost.
