---
description: 睡覺：收工用，= /oct-nap + /oct-dream 一次做完；多視窗時只在最後關的那個跑
---

# oct-sleep

End-of-day wrap-up for the **last window** you're closing today: save this
window's checkpoint, then trigger one global `/oct-dream` pass.

## Usage

```bash
/oct-sleep              # Save this window + run one global memory consolidation
/oct-sleep --help       # Show help
```

## Multi-window scenario — why this is a separate command from `/oct-nap`

If you work across several Claude Code windows in parallel (different
projects, different tasks), each window should run **`/oct-nap`
individually** when you're done with it — that's cheap, because it reads
that window's own already-warm context.

`/oct-dream` is different: it operates on the **global** `memory/`
directory and the shared `summaries/` checkpoint pool, not anything
window-specific. Running it once is enough — running it once per window
would just redo the same global consolidation redundantly.

So the pattern is:

```
Window A (done for the day):  /oct-nap
Window B (done for the day):  /oct-nap
Window C (the last one):      /oct-sleep   ← save C + one global /oct-dream
```

`/oct-sleep` is exactly `/oct-nap` (for the window it's run in) followed
by `/oct-dream` (global) — it exists so the *last* window you close can
do both in one shot, not because it's a shortcut for typing two commands
in the general case. Don't run it in every window — that defeats the
"dream only needs to happen once" point and wastes a redundant
consolidation pass each time.

**Considered and rejected**: making `/oct-sleep` save *all* open windows
by itself, from a single command. Technically possible (read the other
windows' `.jsonl` transcripts off disk), but that means cold-reading their
full context into *this* window just to summarize it — the same expensive
cache-miss cost `/oct-wake` exists to avoid in the first place. Each
window saving itself, using its own warm context, stays the cheap path.

## What It Does

1. **Save this window** — same as `/oct-nap`: write a ~1-2k token
   checkpoint to `~/.claude/summaries/{hash}.md`.
2. **Run `/oct-dream`** — global consolidation pass: Checkpoint Sweep
   (archive candidates from `summaries/`) + the usual `memory/`
   organization. See `oct-dream.md` for the full behavior — `/oct-sleep`
   doesn't reimplement it, it just also triggers it.

## Workflow

```
Per window, as you finish with it:  /oct-nap
Last window of the day:             /oct-sleep
Next session, any window:           /oct-wake
```

## Tips

- If you only ever run one window at a time, `/oct-sleep` and
  `/oct-nap` + `/oct-dream` back-to-back are equivalent — use whichever
  you remember.
- Don't run `/oct-sleep` in every window of a multi-window day — just the
  last one you close. The others just need `/oct-nap`.
