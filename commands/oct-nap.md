---
description: 小睡：離開或 /clear 前，把「做到哪、發現什麼、接下來幹嘛」寫成 ~1-2k token 的便條到 ~/.claude/summaries/
---

# oct-nap

Save current session state as a checkpoint before clearing context.

## Usage

```bash
/oct-nap              # Save session summary
```

## What It Does

Creates a lightweight handoff note (~1-2k tokens) that captures:
- What you were working on
- Key findings and decisions
- Next steps
- Related memory files
- Short-term context

Saves to `~/.claude/summaries/{hash}.md` for use with `/oct-wake`.

## Format

```markdown
# a1b2c3d4 | 2026-08-21 16:45

## Task
[what the user was working on]

## Due
[optional — omit entirely unless the user actually said something with a
deadline/urgency during this session, e.g. "9/15 前回覆 Mikhail" or "這個很
急". Write it close to their words: a date if they gave one (YYYY-MM-DD),
otherwise the urgency phrase as-is. Never infer a due date from ticket
priority, file names, or your own judgment of importance — only from what
the user actually said.]

## Key Findings
- [important discoveries or decisions]

## Next Steps
- [ ] [concrete, checkable next action]
- [ ] [next action after that]

## Related Memory Files
- [relevant memory files]

## Important Context
- [anything that would be lost after /clear]
```

## Instructions

1. Generate the summary in the format above. Include `## Due` only if the
   session actually contained a deadline/urgency statement from the user —
   leave it out entirely otherwise, don't write it empty or guess one.
   Write `## Next Steps` as an actual todo list — break the remaining work
   into separate `- [ ]` items rather than one vague line, so `/oct-wake`
   can show progress and you can tick items off across multiple wake/nap
   cycles on the same task instead of re-deriving "what's left" from scratch
   each time.
   If this `/oct-nap` is re-saving over the same task (you already have an
   open checkpoint's hash from this session, e.g. via `/oct-wake`), carry
   its `- [x]` items forward as done instead of resetting the list to all
   unchecked.
2. Save it to `~/.claude/summaries/{8-char-hash}.md` using the Write tool.
3. Output only:

```
✅ ~/.claude/summaries/{hash}.md
```

Do NOT print the summary content.
