---
description: "Second opinion — dispatch a clean cold sub-agent with a neutral brief to decide; no model switch, no clearing. `--here` re-evaluates in the current model instead."
---

# oct-consult

Default: Mode A. Skip Mode A only if:
- the session is ending in the higher tier anyway: just `/model <higher-tier>`;
- 3+ more turns with the bigger model are needed, or the decision depends on context too specific to write into a brief: `/model <higher-tier>`, then `/oct-consult --here`.

`$ARGUMENTS`:
- empty: Mode A about the most recently discussed decision
- `<keyword>`: Mode A about the decision the keyword points to
- `--here`: Mode B (combinable with a keyword)

## Mode A: cold sub-agent

Do not switch model or clear the conversation.

1. Write a neutral brief (no recommendation, no leaning):
   ```
   ## Question (one line)
   ## Facts (bulleted, with file paths/line numbers so the agent can verify)
   ## Options (a1/a2/a3…, one line each, unordered)
   ## Constraints (hard constraints already agreed on)
   ## What to return (list what you'd push back on first, then a conclusion + one-line reason; ≤300 words)
   ```
   End the brief with: read the files listed above before deciding; if the brief and the files disagree, the files win — say so.
2. Call `Agent(subagent_type: "general-purpose", model: "opus", description: "cold decision: <topic>", prompt: brief)`.
   If opus is unavailable on the user's plan, tell the user; do not silently use another model.
   No fork. No background run.
3. Relay only the conclusion and the objections raised; do not reprint the brief.
4. If several decisions are pending, put them all in one brief and spawn once.

## Mode B (`--here`)

Do not assume the conclusion already reached in this conversation is right. List the objections you would otherwise raise first, then give your own conclusion.
