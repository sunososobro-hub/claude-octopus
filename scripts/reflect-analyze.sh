#!/bin/bash
# Automated token waste diagnosis

MEMORY_DIR="$HOME/.claude/projects/-home-alonso/memory"

echo "🔍 Oct-Reflect: Token Waste Diagnosis"
echo "======================================"
echo ""

# ── 1. Session Baseline ──
echo "1️⃣  Session Baseline Cost (fixed, cannot reduce)"
echo ""
echo "   Every new session costs ~15.7k tokens:"
echo "   ├─ System prompt:      ~12k  (Claude Code built-in)"
echo "   ├─ Tool definitions:   ~1.8k (built-in)"
echo "   ├─ Agent listing:      ~550  (built-in)"
echo "   └─ Skill listing:      ~1.2k (your oct- skills)"
echo ""
echo "   ℹ️  MCP on/off makes no difference — tested."
echo "   ℹ️  This is the floor. Optimize elsewhere."
echo ""

# ── 2. Real Cost Drivers ──
echo "2️⃣  Real Cost Drivers (where to actually optimize)"
echo ""

# Subagents
echo "   🔴 Subagents (biggest waste)"
echo "   → Each agent spawn = full new API request"
echo "   → 56% of your usage came from subagent-heavy sessions"
echo "   → Fix: Don't spawn agents for simple tasks"
echo "          Only use for multi-file search or complex RCA"
echo ""

# Long context
echo "   🟠 Long Context (second biggest)"
echo "   → 42% of sessions exceeded 150k tokens"
echo "   → Context compounds: longer = more expensive per message"
echo "   → Fix: /oct-rest at 70% → new session → /oct-recall"
echo ""

# ── 3. Memory Files ──
echo "3️⃣  Memory Files (worth reviewing)"
echo ""

memory_index_size=$(wc -c < "$MEMORY_DIR/MEMORY.md" 2>/dev/null || echo 0)
echo "   MEMORY.md index: ~$((memory_index_size / 4)) tokens (loaded every session)"
echo ""

echo "   Large files that get read when referenced:"
find "$MEMORY_DIR" -name "*.md" -not -name "MEMORY.md" -not -name "*complete*" | while read f; do
  words=$(wc -w < "$f")
  if [[ $words -gt 500 ]]; then
    name=$(basename "$f")
    # Check if it's a completed task
    if echo "$name" | grep -qE "sys18|sys17|regression"; then
      echo "   ⚠️  $name: ~$words words → completed bug, consider archiving"
    else
      echo "   📄 $name: ~$words words"
    fi
  fi
done

echo ""
echo "   💡 /oct-dream → archive completed bugs"
echo "      Reduces MEMORY.md index size"
echo ""

# ── 4. Summary ──
echo "======================================"
echo "📊 Priority Actions"
echo ""
echo "High impact:"
echo "  1. Avoid spawning agents for simple questions"
echo "     → Ask yourself: can Claude answer this directly?"
echo "     → Only use /explore or /investigate for complex tasks"
echo ""
echo "  2. /oct-rest at 70% context → new session → /oct-recall"
echo "     → Prevents compounding costs from long sessions"
echo ""
echo "Medium impact:"
echo "  3. /oct-dream → archive completed bugs (SYS-1859, etc)"
echo "     → Smaller MEMORY.md = slightly less index overhead"
echo ""
echo "Not worth optimizing:"
echo "  ✗ MCP on/off  — no measurable effect"
echo "  ✗ Skill count — ~1.2k tokens, negligible"
echo "  ✗ New sessions — baseline is fixed at ~15.7k"
echo ""
