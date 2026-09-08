# oct-usage

Show per-request token usage and cost for the current session.

## Usage

```bash
/oct-usage                  # Current session, table view
/oct-usage --current        # Current session + context size estimate
/oct-usage --detail         # Add tier/speed/geo/web columns
/oct-usage --summary        # Aggregated totals by token type
/oct-usage <session-id>     # Specific session (partial ID ok)
/oct-usage --last=N         # Last N calls only
```

## Default Table

```
📊 oct-usage  |  session: d76c8f77  |  2026-08-21  |  20 API calls

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
