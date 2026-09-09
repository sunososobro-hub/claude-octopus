#!/bin/bash
# oct-benchmark.sh — compare claude --resume vs oct-wake for the same prompt
#
# Usage:
#   oct-benchmark.sh <session-id> <checkpoint.md> ["test prompt"]
#   oct-benchmark.sh --auto                        # auto-pick largest session + latest checkpoint
#   oct-benchmark.sh --sweep [N] [checkpoint.md]    # N real sessions spread across your own
#                                                    # history's size range (default N=6), one
#                                                    # fixed checkpoint, prints a summary table
#
# Example:
#   oct-benchmark.sh 4ca2278f ~/.claude/summaries/51e6f5cf.md "summarize what we did"
#   oct-benchmark.sh --sweep 8

set -e

PROMPT="${3:-hello, what were we working on?}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
# Pin the same model for both [A] and [B]. Left to the CLI default, a fresh
# -p session can land on a different model version than an old resumed
# session, which blows the shared tool-definition prompt cache for whichever
# side misses — that one-time cache miss (100K+ tokens) has nothing to do
# with resume-vs-checkpoint and will dominate the comparison if not pinned.
MODEL="${OCT_BENCH_MODEL:-sonnet}"
ANALYZE="python3 $(dirname "$0")/usage-analyze.py"
SELF="$0"

# ── sweep mode ─────────────────────────────────────────────────────────────
# Picks N real sessions from your own history, spread log-scale across the
# size range you actually have (smallest to largest), and re-invokes this
# same script once per session (reusing the single-pair path below, including
# its model pinning and session-scoped result capture). One fixed checkpoint
# throughout, so session size is the only thing that varies between rows.
if [[ "$1" == "--sweep" ]]; then
  N="${2:-6}"
  CHECKPOINT="${3:-$(ls -t ~/.claude/summaries/*.md 2>/dev/null | grep -v archive | head -1)}"
  if [[ -z "$CHECKPOINT" || ! -f "$CHECKPOINT" ]]; then
    echo "No checkpoint found (looked in ~/.claude/summaries/). Pass one explicitly: --sweep $N <checkpoint.md>"
    exit 1
  fi
  echo "🔬 oct-benchmark sweep — $N sessions, model=$MODEL, checkpoint=$CHECKPOINT"
  echo ""

  SESSION_LIST=$(python3 - "$N" <<'EOF'
import json, math, pathlib, sys

n = int(sys.argv[1])
projects = pathlib.Path.home() / ".claude" / "projects"
sizes = {}
for jsonl in projects.rglob("*.jsonl"):
    sid = jsonl.stem
    if sid.startswith("agent-"):
        continue
    last_ctx = None
    try:
        for line in jsonl.read_text(errors="ignore").splitlines():
            try:
                ev = json.loads(line)
                usage = ev.get("message", {}).get("usage", {})
                if usage:
                    last_ctx = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            except Exception:
                pass
    except Exception:
        pass
    if last_ctx and last_ctx > 3000:
        sizes[sid] = last_ctx

items = sorted(sizes.items(), key=lambda x: x[1])
if not items:
    sys.exit(0)

lo, hi = items[0][1], items[-1][1]
picked, seen = [], set()
for i in range(n):
    frac = i / max(n - 1, 1)
    target = math.exp(math.log(max(lo, 1)) + frac * (math.log(max(hi, 1)) - math.log(max(lo, 1))))
    candidates = [kv for kv in items if kv[0] not in seen]
    if not candidates:
        break
    best = min(candidates, key=lambda kv: abs(kv[1] - target))
    seen.add(best[0])
    picked.append(best)

for sid, ctx in picked:
    print(f"{sid} {ctx}")
EOF
  )

  if [[ -z "$SESSION_LIST" ]]; then
    echo "No real sessions with usable history found."
    exit 1
  fi

  RESULTS_FILE=$(mktemp)
  while read -r SID CTX; do
    [[ -z "$SID" ]] && continue
    echo "── $SID  (~${CTX} tokens before) ──────────────────────"
    # </dev/null: the recursive call's own `claude -p` otherwise inherits this
    # loop's stdin (the `<<< "$SESSION_LIST"` herestring) — if it reads from
    # it at all, that drains the herestring and the outer `while read` loop
    # silently stops after one iteration.
    # || true: a single trial failing (e.g. a session too big for $MODEL's
    # context window) must not take down the rest of the sweep via set -e.
    OUT=$("$SELF" "$SID" "$CHECKPOINT" "hello, what were we working on?" 2>&1 </dev/null) || true
    echo "$OUT" | tail -6
    # Each pipe ends in a bare grep (no fallback command after it), so a
    # non-matching trial — the normal case for a skipped/failed one — makes
    # the pipe exit 1 and, under set -e, kill the whole sweep. `|| true` on
    # every extraction keeps a failed trial to just one skipped row.
    A=$(echo "$OUT"  | grep -oE '\[A\] resume   tokens≈[0-9,]+' | grep -oE '[0-9,]+$' | tr -d ',' || true)
    ACOST=$(echo "$OUT" | grep -oE '\[A\] resume   tokens≈[0-9,]+  cost=\$[0-9.]+' | grep -oE '[0-9.]+$' || true)
    B=$(echo "$OUT"  | grep -oE '\[B\] oct-wake tokens≈[0-9,]+' | grep -oE '[0-9,]+$' | tr -d ',' || true)
    BCOST=$(echo "$OUT" | grep -oE '\[B\] oct-wake tokens≈[0-9,]+  cost=\$[0-9.]+' | grep -oE '[0-9.]+$' || true)
    if [[ -n "$A" && -n "$B" && "$A" != "0" && -n "$ACOST" && -n "$BCOST" ]]; then
      echo "${SID:0:8}|$A|$ACOST|$B|$BCOST" >> "$RESULTS_FILE"
    else
      echo "  ⚠ skipped — resume failed or was unparseable (session likely exceeds ${MODEL}'s context window)"
    fi
    echo ""
  done <<< "$SESSION_LIST"

  echo "════════════════════════════════════════"
  echo "  Sweep summary ($(wc -l < "$RESULTS_FILE" 2>/dev/null || echo 0) of $N usable)"
  echo "════════════════════════════════════════"
  printf "%-10s  %14s  %10s  %14s  %10s  %10s\n" "session" "resume tok" "resume \$" "wake tok" "wake \$" "cost saved"
  while IFS='|' read -r SID A ACOST B BCOST; do
    python3 - "$SID" "$A" "$ACOST" "$B" "$BCOST" <<'PYEOF'
import sys
sid, a, ac, b, bc = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
saved = (1 - bc / ac) * 100 if ac > 0 else 0
print(f"{sid:<10}  {a:>14,.0f}  ${ac:>9.4f}  {b:>14,.0f}  ${bc:>9.4f}  {saved:>9.0f}%")
PYEOF
  done < "$RESULTS_FILE"
  rm -f "$RESULTS_FILE"
  exit 0
fi

# ── auto mode ──────────────────────────────────────────────────────────────
if [[ "$1" == "--auto" ]]; then
  # Pick the session whose LAST call had the biggest context (that's what
  # --resume would actually reload). Summing tokens across every call in the
  # session (the old approach) massively overcounts — a long session re-reads
  # nearly the same context on every turn, so the sum is roughly
  # context_size × call_count, not context_size.
  SESSION_ID=$(python3 - <<'EOF'
import json, pathlib

projects = pathlib.Path.home() / ".claude" / "projects"
session_last = {}

for jsonl in projects.rglob("*.jsonl"):
    session_id = jsonl.stem
    last_ctx = None
    try:
        for line in jsonl.read_text(errors="ignore").splitlines():
            try:
                ev = json.loads(line)
                usage = ev.get("message", {}).get("usage", {})
                if usage:
                    last_ctx = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            except Exception:
                pass
    except Exception:
        pass
    if last_ctx:
        session_last[session_id] = last_ctx

best = max(session_last, key=session_last.get)
print(best)
EOF
  )
  # Pick the latest checkpoint
  CHECKPOINT=$(ls -t ~/.claude/summaries/*.md 2>/dev/null | grep -v archive | head -1)
  echo "Auto-selected session: $SESSION_ID"
  echo "Auto-selected checkpoint: $CHECKPOINT"
else
  SESSION_ID="$1"
  CHECKPOINT="$2"
fi

if [[ -z "$SESSION_ID" || -z "$CHECKPOINT" ]]; then
  echo "Usage: oct-benchmark.sh <session-id> <checkpoint.md> [\"prompt\"]"
  echo "       oct-benchmark.sh --auto"
  exit 1
fi

if [[ ! -f "$CHECKPOINT" ]]; then
  echo "Error: checkpoint not found: $CHECKPOINT"
  exit 1
fi

echo ""
echo "════════════════════════════════════════"
echo "  oct-benchmark"
echo "  Session : $SESSION_ID"
echo "  Prompt  : $PROMPT"
echo "════════════════════════════════════════"
echo ""

# ── run A: claude --resume ──────────────────────────────────────────────────
echo "▶ [A] claude --resume $SESSION_ID (model: $MODEL) ..."
$CLAUDE_BIN --model "$MODEL" --resume "$SESSION_ID" -p "$PROMPT" > /dev/null 2>&1 || true
sleep 2

# capture last API call from usage-analyze — scoped to $SESSION_ID explicitly.
# An unscoped query (just "most recent call across all projects") is a race:
# if anything else logs a call in that window, you silently score the wrong
# session instead of this one.
A_LINE=$(python3 - <<EOF
import subprocess, sys
result = subprocess.run(
    ["python3", "$(dirname "$0")/usage-analyze.py", "$SESSION_ID", "--last=1", "--reverse"],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    line = line.strip()
    if line and line[0].isdigit():
        print(line)
        break
EOF
)
echo "  → $A_LINE"

# ── run B: oct-wake (new session with checkpoint) ──────────────────────────
echo ""
echo "▶ [B] oct-wake (new session + checkpoint, model: $MODEL) ..."
CHECKPOINT_CONTENT=$(cat "$CHECKPOINT")
PROJECT_DIR="$HOME/.claude/projects/$(pwd | sed 's/\//-/g')"
BEFORE_NEWEST=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
$CLAUDE_BIN --model "$MODEL" -p "$(printf '%s\n\n---\n%s' "$CHECKPOINT_CONTENT" "$PROMPT")" > /dev/null 2>&1 || true
sleep 2

# The fresh -p call creates a brand-new session file in this project's
# transcript dir. Find it by diffing against what was newest before we ran,
# instead of an unscoped "most recent anywhere" query (same race as above).
B_SESSION_ID=$(python3 - "$PROJECT_DIR" "$BEFORE_NEWEST" <<'PYEOF'
import pathlib, sys
project_dir, before_newest = sys.argv[1], sys.argv[2] or None
files = sorted(pathlib.Path(project_dir).glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
for f in files:
    if str(f) != before_newest:
        print(f.stem)
        break
else:
    if files:
        print(files[0].stem)
PYEOF
)

B_LINE=$(python3 - <<EOF
import subprocess
result = subprocess.run(
    ["python3", "$(dirname "$0")/usage-analyze.py", "$B_SESSION_ID", "--last=1", "--reverse"],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    line = line.strip()
    if line and line[0].isdigit():
        print(line)
        break
EOF
)
echo "  → $B_LINE"

# ── compare ─────────────────────────────────────────────────────────────────
echo ""
python3 - "$A_LINE" "$B_LINE" <<'EOF'
import sys, re

def parse_cost(line):
    # extract CacheRead tokens and Cost
    m_read = re.search(r'([\d.]+)K\(\$[\d.]+\)\s+[\d.]+K\(\$[\d.]+\)', line)
    m_cost = re.search(r'\$([\d.]+)\s*$', line.strip())
    # total tokens = In + CacheRead + CacheWrite + Out (rough)
    tokens = sum(
        float(x.replace('K','')) * (1000 if 'K' in orig else 1)
        for orig, x in [(t, re.sub(r'\(.*?\)','',t).strip())
                        for t in re.findall(r'[\d.]+K?\(\$[\d.]+\)', line)]
    )
    cost = float(m_cost.group(1)) if m_cost else 0
    return tokens, cost

a_line, b_line = sys.argv[1], sys.argv[2]
a_tok, a_cost = parse_cost(a_line)
b_tok, b_cost = parse_cost(b_line)

if a_tok == 0 or b_tok == 0:
    print("Could not parse token counts. Raw output above.")
    sys.exit(0)

tok_save = (1 - b_tok / a_tok) * 100 if a_tok > 0 else 0
cost_save = (1 - b_cost / a_cost) * 100 if a_cost > 0 else 0

print("════════════════════════════════════════")
print(f"  [A] resume   tokens≈{a_tok:,.0f}  cost=${a_cost:.4f}")
print(f"  [B] oct-wake tokens≈{b_tok:,.0f}  cost=${b_cost:.4f}")
print("────────────────────────────────────────")
print(f"  Token saved : {tok_save:.0f}%")
print(f"  Cost  saved : {cost_save:.0f}%")
print("════════════════════════════════════════")
EOF
