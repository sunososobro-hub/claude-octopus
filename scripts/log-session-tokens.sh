#!/bin/bash
# Record current session's token usage to token-log.md

TOKEN_LOG="$HOME/.claude/token-log.md"
CHECKPOINT_NAME="${1:-checkpoint}"
TASK_NAME="${2:-general}"

# Initialize token log if it doesn't exist
if [[ ! -f "$TOKEN_LOG" ]]; then
  {
    echo "# Token Usage Log"
    echo ""
    echo "Automated token tracking for all sessions."
    echo "Populated by /oct-rest (checkpoint) and /oct-sleep (session end)."
    echo ""
    echo "---"
    echo ""
  } > "$TOKEN_LOG"
fi

# Get current timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

# Prompt user for token info (since we can't directly parse /stats output)
echo "📊 Record Session Tokens"
echo ""
echo "From /stats, enter:"
read -p "Model used (Fable/Sonnet/Haiku): " model
read -p "Input tokens: " input_tokens
read -p "Output tokens: " output_tokens
read -p "Cache read tokens: " cache_tokens
read -p "Cost (USD): " cost

# Calculate totals
total_tokens=$((input_tokens + output_tokens + cache_tokens))

# Append to log
{
  echo "## $TIMESTAMP - $CHECKPOINT_NAME"
  echo "**Task:** $TASK_NAME"
  echo "**Model:** $model"
  echo ""
  echo "| Metric | Value |"
  echo "|--------|-------|"
  echo "| Input tokens | $input_tokens |"
  echo "| Output tokens | $output_tokens |"
  echo "| Cache read | $cache_tokens |"
  echo "| Total | $total_tokens |"
  echo "| Cost (USD) | \$$cost |"
  echo ""
  echo "---"
  echo ""
} >> "$TOKEN_LOG"

echo "✓ Logged to $TOKEN_LOG"
