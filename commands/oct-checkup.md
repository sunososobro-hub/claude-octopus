---
description: 健檢：列出這個對話每次呼叫的 token/花費明細；`habits` 掃最近的對話找浪費模式、建議可存成記憶的規則
---

# oct-checkup

Show per-request token usage and cost for the current session. With
`habits`, scan recent transcripts for spending patterns and propose
memory rules that would fix them.

## Usage

```bash
/oct-checkup                # Current session, table view
/oct-checkup --current      # Current session + context size estimate
/oct-checkup --detail       # Add tier/speed/geo/web columns
/oct-checkup --summary      # Aggregated totals by token type
/oct-checkup <session-id>   # Specific session (partial ID ok)
/oct-checkup --last=N       # Last N calls only
/oct-checkup habits         # Waste patterns in the last 7 days + suggested rules
/oct-checkup habits 30      # ...over the last 30 days
```

## Habits (`/oct-checkup habits [days]`)

The numbers above tell you *what* you spent; this tells you *which habit*
spent it. Python reads the transcripts (`~/.claude/projects/**/*.jsonl`) —
Claude never does — and prints a bounded report with at most two examples
per pattern. Patterns it looks for:

1. **Wall then question** — Claude answered with a long block (or 5+
   numbered steps) and the very next user message was a short question.
   The answer didn't land; every follow-up re-reads the whole context.
2. **Fat-context chatter** — turns where context was already >100K and the
   user said something tiny. Each one costs a full cache read.
3. **Repeated corrections** — user messages starting with 不要/不用/別/
   don't/stop/… across sessions. A correction said twice should be a
   memory rule.
4. **Fat session, no nap** — a session ended with >80K context and no
   checkpoint was written around that time. The next `--resume` is a cold
   re-read.
5. **Corrected again right after auto-compact** — a correction-keyword
   message lands within 30 minutes of an auto-compact boundary in the same
   session. Timing-coincidence check only (not proven causally related) —
   suggests a rule that was living in the conversation got diluted by
   compaction instead of actually being retained; the fix is to move that
   rule into CLAUDE.md (global or project-level) instead of relying on it
   surviving inside the conversation.

The scan also self-times: if it takes ≥8s (it's supposed to be a cheap
local pass), it prints a note with just the elapsed seconds and session
count, and a link to open an issue — no conversation content, and nothing
is ever sent automatically. Purely a local print, so the tool that's
supposed to save you tokens doesn't quietly become the thing wasting your
time.

Run:

```bash
python3 ~/.claude/scripts/usage-analyze.py --habits            # 7 days
python3 ~/.claude/scripts/usage-analyze.py --habits --days=30
```

Print the report as-is in a code block. It ends with a question — which
suggestions to save. Wait for the answer.

For each one the user accepts, write a **feedback** memory into the
project's memory directory (the one named in your system prompt's
auto-memory section; `~/.claude/projects/<slug>/memory/`), using the
standard shape — frontmatter `name` / `description` / `metadata.type:
feedback`, then the rule, a **Why:** line citing the pattern and its cost
from the report, and a **How to apply:** line — and add a one-line pointer
to `MEMORY.md`. Check for an existing memory covering the same rule first
and update it instead of duplicating.

Confirm only: `✅ Saved: feedback_step_by_step, feedback_nap_before_leaving`
— don't echo the memory content back. If the user says no to all, say
nothing more.

If the report says no patterns were found, that's the whole answer.

## Default Table

```
📊 oct-checkup  |  session: d76c8f77  |  2026-08-21  |  20 API calls

   #  Timestamp            Model                 In       CacheRead      CacheWrite            Out      Cost
──────────────────────────────────────────────────────────────────────────────────────────────────────────
   1  2026-08-21 10:30:01  sonnet-4-6    6($0.00)  23.3K($0.01)   16.3K($0.06)     678($0.01)  $0.0782
   2  2026-08-21 10:31:45  sonnet-4-6    6($0.00)  40.3K($0.01)      96($0.00)    1.6K($0.02)  $0.0366
...
──────────────────────────────────────────────────────────────────────────────────────────────────────────
      Total                             152($0.00) 2417K($0.73)   76.5K($0.29)   40.1K($0.60)  $1.6144
```

Columns:
- **In** — fresh input tokens
- **CacheRead** — cache read tokens (cheap)
- **CacheWrite** — cache write tokens
- **Out** — output tokens
- **Cost** — actual USD, per-model pricing

## Detail Mode (`--detail`)

Adds columns: `1h` (1h cache write), `5m` (5m cache write), `🔍` (web search), `🌐` (web fetch), `Tier`, `Speed`.

## Pricing (per model)

| Model | Input | Output | Cache Write | Cache Read |
|-------|-------|--------|-------------|------------|
| Fable 5 | $10 | $50 | $12.50 | $1.00 |
| Opus 4.8 | $5 | $25 | $6.25 | $0.50 |
| Sonnet 4.6 | $3 | $15 | $3.75 | $0.30 |
| Haiku 4.5 | $1 | $5 | $1.25 | $0.10 |

($/MTok)

## How to Run

Run: `python3 ~/.claude/scripts/usage-analyze.py --last=20 --reverse` to show current session table. Or `python3 ~/.claude/scripts/usage-analyze.py` (no args) to list all sessions.

Then read the saved output file if truncated, and print the FULL content directly as a plain code block in your response text. Do NOT just show the bash tool result — the user must see the table in chat.

If the header says "共 N 筆" where N > 20, append a note after the code block: "（顯示最新 20 筆，共 N 筆。輸入 `--last=50` 看更多）"
