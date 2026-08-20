#!/bin/bash
# claude-octopus installer

COMMANDS_DIR="$HOME/.claude/commands"
SUMMARIES_DIR="$HOME/.claude/summaries"

mkdir -p "$COMMANDS_DIR" "$SUMMARIES_DIR"

echo "Installing claude-octopus commands..."

# Session tools
cp session/oct-sessions.md "$COMMANDS_DIR/oct-sessions.md"
cp session/oct-summary.md  "$COMMANDS_DIR/oct-summary.md"
cp session/oct-load.md     "$COMMANDS_DIR/oct-load.md"

echo "Done. Commands installed:"
echo "  /oct-sessions  — browse session history"
echo "  /oct-summary   — save current session as a handoff note"
echo "  /oct-load      — restore a previous session"
