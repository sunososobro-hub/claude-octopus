#!/bin/bash
# Analyze token usage from token-log.md

TOKEN_LOG="$HOME/.claude/token-log.md"
PERIOD="${1:-all}"

if [[ ! -f "$TOKEN_LOG" ]]; then
  echo "❌ No token log found"
  echo "Use /oct-rest or /oct-sleep to start recording"
  exit 1
fi

echo "🔍 Token Reflection Report"
echo ""

# Parse token log and calculate totals
echo "Analyzing token log..."
echo ""

# Extract all entries
grep -E "^\## |Model:|Cost" "$TOKEN_LOG" | while read -r line; do
  echo "$line"
done

echo ""
echo "📊 Quick Stats:"
echo ""

# Sum costs
total_cost=$(grep "| Cost" "$TOKEN_LOG" | grep -oE '\$[0-9.]+' | sed 's/\$//' | awk '{sum+=$1} END {print sum}')
entry_count=$(grep -c "^\## " "$TOKEN_LOG")

echo "Total entries: $entry_count"
echo "Total cost: \$$total_cost"
echo ""

# Model breakdown (simple)
echo "Model Usage:"
grep "Model:" "$TOKEN_LOG" | sort | uniq -c

echo ""
echo "💡 For detailed analysis, check: $TOKEN_LOG"
