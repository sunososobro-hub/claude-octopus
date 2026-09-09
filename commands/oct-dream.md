---
description: 做夢：整理記憶——合併重複、歸檔做完的便條、抽出反覆出現的模式
---

# oct-dream

Consolidate and organize memories after a work session.

Like processing experiences during sleep — extract patterns, merge related items, archive completed work.

Also sweeps `~/.claude/summaries/` (the `/oct-nap` checkpoints `/oct-wake` reads) —
not just the long-term `memory/` directory — see "Checkpoint Sweep" below.

## Usage

```bash
/oct-dream              # Start memory consolidation
/oct-dream --help       # Show help
/oct-dream help         # Show help
```

## What It Does

After `/oct-sleep`, consolidate your memories by choosing an organization strategy:

```
🌙 Memory Consolidation

Detected: 8 sessions, 10 related memories this week

Choose organization method:

1️⃣ Auto Recommend
   System analyzes → suggests best plan
   Speed: ⚡ Fast | Control: Lower
   
2️⃣ Manual Select
   You decide each item → full control
   Speed: 🐢 Slow | Control: Complete
   
3️⃣ By Task
   Group by SYS-1859, SYS-1844, etc
   Best for: Finding related items quickly
   
4️⃣ By Timeline
   Week 1: Discovery | Week 2: Analysis | Week 3: Fix
   Best for: Reviewing progress
   
5️⃣ Extract Patterns
   Find recurring patterns & decision rules
   Best for: Long-term learning

Choose: [1-5] or multiple?
```

## Checkpoint Sweep

`/oct-nap` checkpoints in `~/.claude/summaries/*.md` (excluding the
`.last_woken` marker) accumulate over time — `/oct-wake` only shows recent
ones by default, but old ones never actually go away on their own.

**Don't decide by age alone** — an old checkpoint isn't automatically
irrelevant (the user may genuinely still be mid-task on something they
haven't touched in weeks). Instead, scan each checkpoint's content for
completion signals: task title or `## Next Steps`/`## 下一步` containing
words like 完結/已完成/done/committed, or a next-steps section that's
empty/resolved.

1. List candidates that look done, grouped by evident project/ticket
   (e.g. multiple `sys1874*` checkpoints for the same ticket). Number
   them (1, 2, 3...) — never make the user refer back to an 8-char hash
   to answer.
2. For each, give a one-line recommendation (archive or keep) with the
   reason, not just a bare list — the user shouldn't have to re-derive
   the judgment themselves. Ask once, in a form that accepts a single
   bulk answer ("全部歸檔" / "都可以" / "2,4 不要" etc.) — never make the
   user answer item-by-item; that's the friction this whole batching
   exists to avoid. Never archive silently regardless of how confident
   the recommendation is — a bulk "yes" from the user is still required.
3. For confirmed ones: `mkdir -p ~/.claude/summaries/archive` and move the
   file there (`git mv`-style — just relocate, don't delete or rewrite
   content).
4. If a checkpoint's content would still be valuable long-term (a
   decision, a gotcha, a pattern — not just "what I was doing"), also
   fold the relevant bit into the normal `memory/` consolidation below,
   the same as any other source. **When a project/ticket group has 2 or
   more checkpoints just confirmed for archive in this same sweep, don't
   fold each one separately** — merge them into a single consolidated
   `memory/` entry telling the project's story across those sessions
   (what happened, in order, plus any decisions/gotchas), instead of
   leaving scattered fragments the user has to piece back together.
   Checkpoints still in progress (not confirmed for archive) are never
   merged this way — only ones the user just approved archiving.

After the sweep, `/oct-wake` (default view) will naturally show a shorter,
more current list since archived checkpoints move out of the directory it
scans; `/oct-wake --all` still shows both active and archived.

## After Consolidation

Shows final structure:

```
✅ Memory Organized

memory/
├─ tasks/
│  ├─ SYS-1859/
│  │  ├─ summary.md
│  │  ├─ snapshot_strategy.md
│  │  └─ sessions/ (3 checkpoints)
│  ├─ SYS-1844/
│  │  └─ summary.md
│  └─ ...
├─ patterns/
│  ├─ model_selection.md
│  ├─ auto_routing.md
│  └─ ...
├─ feedback/
│  └─ ...
└─ archive/
   └─ completed-2026-08/

📊 Changes:
   New memories: 3
   Merged: 2
   Archived: 1
   Optimization: 15%
```

## Organization Methods

**1. Auto Recommend**
- System finds duplicates
- Suggests merges and archives
- Fast but may miss your intent

**2. Manual Select**
- Review each memory
- Decide: keep, merge, delete, archive
- Slowest but most control

**3. By Task**
```
tasks/
├─ SYS-1859/
├─ SYS-1844/
├─ feature-xyz/
└─ ...
```
Best for: Project-based work

**4. By Timeline**
```
progress/
├─ week-1-discovery/
├─ week-2-analysis/
├─ week-3-implementation/
└─ ...
```
Best for: Progress tracking & learning

**5. Extract Patterns**
```
patterns/
├─ model_selection_guide.md
├─ context_bloat_solution.md
├─ debugging_approach.md
└─ ...
```
Best for: Building your personal knowledge base

## Typical Workflow

```
Day: /oct-wake → work → /oct-sleep
Week: /oct-sleep → /oct-dream (organize) → ready for next week
```

## Tips

- Run `/oct-dream` weekly or after major milestones
- Try different organization methods to see what works
- Patterns you extract become guides for future work
- Archived memories stay accessible, just hidden
