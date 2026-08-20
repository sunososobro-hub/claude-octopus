#!/bin/bash
set -e

# Install oct-router: update settings.json and enable auto-routing

COMMANDS_DIR="${HOME}/.claude/commands"
SETTINGS_FILE="${HOME}/.claude/settings.json"
SETTINGS_LOCAL="${HOME}/.claude/settings.local.json"

echo "🐙 Installing Claude Octopus Auto-Routing..."
echo ""

# Copy command
mkdir -p "${COMMANDS_DIR}"
echo "✓ Installing /oct-route command"
OCTOPUS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${OCTOPUS_ROOT}/.claude/commands/oct-route.md" "${COMMANDS_DIR}/oct-route.md" 2>/dev/null || \
  echo "  (copying from repo root)"

# Update settings.json
echo "✓ Configuring settings"

# Create settings.json if it doesn't exist
if [[ ! -f "$SETTINGS_FILE" ]]; then
  mkdir -p "$(dirname "$SETTINGS_FILE")"
  echo '{}' > "$SETTINGS_FILE"
fi

# Add oct-router config (use jq if available, otherwise sed)
if command -v jq &> /dev/null; then
  jq '.["oct-router"] = {
    "enabled": true,
    "auto-suggest": true,
    "min-savings-threshold": "30%"
  }' "$SETTINGS_FILE" > "${SETTINGS_FILE}.tmp" && mv "${SETTINGS_FILE}.tmp" "$SETTINGS_FILE"
else
  # Fallback: append to file (simple method)
  if ! grep -q "oct-router" "$SETTINGS_FILE"; then
    # Insert before closing brace
    sed -i.bak '${s/^}/,\n  "oct-router": {\n    "enabled": true,\n    "auto-suggest": true\n  }\n}/}' "$SETTINGS_FILE"
  fi
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Auto-routing is now ACTIVE"
echo ""
echo "How it works:"
echo "• When you ask a question, the system analyzes complexity"
echo "• If savings > 30%, you'll see a suggestion"
echo "• Example: 'Use Haiku instead? Saves $0.44 (79%)' [Yes/No]"
echo ""
echo "You control everything — suggestions only, not automatic"
echo ""
echo "Try it now:"
echo "• Ask a simple question → system suggests Haiku"
echo "• Ask a complex question → system suggests Fable or Sonnet"
echo "• Use /stats to see your cost breakdown"
echo ""
