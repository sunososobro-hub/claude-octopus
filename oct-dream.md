# oct-dream

Consolidate and organize memories after a work session.

Like processing experiences during sleep — extract patterns, merge related items, archive completed work.

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
