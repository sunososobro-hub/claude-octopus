#!/bin/bash
set -e

# Install oct-router and related tools

OCTOPUS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${OCTOPUS_ROOT}/analysis/oct-router"
COMMANDS_DIR="${HOME}/.claude/commands"
HOOKS_DIR="${HOME}/.claude/hooks"

echo "🐙 Installing Claude Octopus Auto-Router..."
echo ""

# Ensure directories exist
mkdir -p "${COMMANDS_DIR}" "${HOOKS_DIR}" "${TOOLS_DIR}"

# Copy command definitions
echo "✓ Installing /oct-route command"
cp "${OCTOPUS_ROOT}/commands/oct-route.md" "${COMMANDS_DIR}/" 2>/dev/null || \
  cp "${OCTOPUS_ROOT}/.claude/commands/oct-route.md" "${COMMANDS_DIR}/"

# Install hook (optional - ask user)
read -p "Enable auto-routing hook? (suggested: yes) [y/n]: " enable_hook

if [[ "$enable_hook" == "y" ]]; then
  echo "✓ Configuring auto-routing hook"
  mkdir -p "${HOOKS_DIR}"

  cat > "${HOOKS_DIR}/on-message-analyze.sh" <<'HOOK'
#!/bin/bash
# Auto-router hook: Analyzes task complexity before sending
# This is called by Claude Code's hook system

# For now, this is a template.
# Full implementation: evaluate message, suggest model if needed

# TODO:
# 1. Parse incoming message
# 2. Estimate complexity
# 3. Compare with current model
# 4. If significant savings available, notify user
HOOK

  chmod +x "${HOOKS_DIR}/on-message-analyze.sh"
  echo "  Hook installed to: ${HOOKS_DIR}/on-message-analyze.sh"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Run /oct-learning to learn about cost optimization"
echo "2. Use /oct-route before complex tasks to get model suggestions"
echo "3. Check /stats to monitor your token savings"
echo ""
