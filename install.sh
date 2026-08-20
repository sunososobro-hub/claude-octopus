#!/bin/bash
set -e
# claude-octopus installer

COMMANDS_DIR="$HOME/.claude/commands"
SUMMARIES_DIR="$HOME/.claude/summaries"

mkdir -p "$COMMANDS_DIR" "$SUMMARIES_DIR"

echo "🐙 Installing claude-octopus..."
echo ""

# Session tools
echo "✓ Session continuity tools"
cp session/oct-sessions.md "$COMMANDS_DIR/oct-sessions.md"
cp session/oct-summary.md  "$COMMANDS_DIR/oct-summary.md"
cp session/oct-load.md     "$COMMANDS_DIR/oct-load.md"

# Learning & routing tools
echo "✓ Cost optimization tools"
cp .claude/commands/oct-learning.md "$COMMANDS_DIR/oct-learning.md" 2>/dev/null || true
cp .claude/commands/oct-route.md    "$COMMANDS_DIR/oct-route.md" 2>/dev/null || true

chmod +x install-router.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "Available commands:"
echo "  /oct-sessions  — browse session history"
echo "  /oct-summary   — save current session"
echo "  /oct-load      — restore previous session"
echo "  /oct-learning  — learn about cost optimization [NEW]"
echo "  /oct-route     — get model suggestions [NEW]"
echo ""
echo "Next: Run /oct-learning to get started!"
echo ""
