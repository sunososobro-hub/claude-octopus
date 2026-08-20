#!/bin/bash
# Get current session file size and estimate tokens

PROJECTS_DIR="$HOME/.claude/projects"

# Find most recently modified .jsonl file
LATEST_SESSION=$(find "$PROJECTS_DIR" -name "*.jsonl" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

if [[ -z "$LATEST_SESSION" ]]; then
  echo "❌ No session found"
  exit 1
fi

# Get file size in bytes and human readable
SIZE_BYTES=$(stat -f%z "$LATEST_SESSION" 2>/dev/null || stat -c%s "$LATEST_SESSION" 2>/dev/null)
SIZE_KB=$((SIZE_BYTES / 1024))

# Estimate tokens (rough: 1 MB ≈ 5000 tokens)
# 1 KB ≈ 5 tokens
ESTIMATED_TOKENS=$((SIZE_KB * 5))

# Context window estimate (Haiku: 128k, Sonnet: 200k, Fable: 300k)
# Use 200k as average
CONTEXT_LIMIT=200000
USAGE_PERCENT=$((ESTIMATED_TOKENS * 100 / CONTEXT_LIMIT))

# Format output
echo "📊 Current Session Context"
echo ""
echo "File size: ${SIZE_KB}K"
echo "Estimated tokens: ~$((ESTIMATED_TOKENS - 100))-$((ESTIMATED_TOKENS + 100))"
echo ""

# Show progress bar
BARS=$((USAGE_PERCENT / 5))
EMPTY=$((20 - BARS))
printf "Usage: "
printf "█%.0s" $(seq 1 $BARS)
printf "░%.0s" $(seq 1 $EMPTY)
printf " %d%%\n" "$USAGE_PERCENT"
echo ""

# Status message
if (( USAGE_PERCENT < 50 )); then
  echo "✅ Healthy — lots of room, work freely"
elif (( USAGE_PERCENT < 75 )); then
  echo "⚠️  Getting full — consider /oct-rest soon"
elif (( USAGE_PERCENT < 90 )); then
  echo "🟠 Close to limit — plan /oct-rest + new agent"
else
  echo "🔴 Critical — do /oct-rest now!"
fi
