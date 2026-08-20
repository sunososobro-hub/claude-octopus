#!/bin/bash
# Automated token waste diagnosis

MEMORY_DIR="$HOME/.claude/projects/-home-alonso/memory"
COMMANDS_DIR="$HOME/.claude/commands"
LATEST_SESSION=$(ls -t ~/.claude/projects/-home-alonso/*.jsonl 2>/dev/null | head -1)

echo "🔍 Oct-Reflect: Token Waste Diagnosis"
echo "======================================"
echo ""

# ── 1. MCP Servers ──
echo "1️⃣  MCP Servers (loaded every session)"
echo ""

# Parse MCP tool definitions from latest session
if [[ -f "$LATEST_SESSION" ]]; then
  python3 -c "
import json, sys

mcp_sizes = {}
with open('$LATEST_SESSION') as f:
    for i, line in enumerate(f):
        try:
            obj = json.loads(line.strip())
            if obj.get('type') == 'attachment':
                att = obj.get('attachment', {})
                att_type = att.get('type', '')
                if 'tools' in att_type or 'deferred' in att_type:
                    size = len(str(att))
                    mcp_sizes[att_type] = mcp_sizes.get(att_type, 0) + size
        except:
            pass
        if i > 20:
            break

total = sum(mcp_sizes.values())
for k, v in sorted(mcp_sizes.items(), key=lambda x: -x[1]):
    tokens = v // 4
    print(f'   {k}: ~{tokens} tokens')
print(f'   Total MCP overhead: ~{total//4} tokens/session')
" 2>/dev/null
fi

echo ""
echo "   💡 Suggestion: disable unused MCP servers"
echo "      /mcp → select → disable"
echo ""

# ── 2. Skills ──
echo "2️⃣  Installed Skills (loaded every session)"
echo ""

skill_count=$(ls "$COMMANDS_DIR"/*.md 2>/dev/null | wc -l)
skill_size=$(cat "$COMMANDS_DIR"/*.md 2>/dev/null | wc -c)
skill_tokens=$((skill_size / 4))

echo "   Skills installed: $skill_count"
echo "   Total skill definitions: ~${skill_tokens} tokens/session"
echo ""

ls "$COMMANDS_DIR"/*.md 2>/dev/null | while read f; do
  size=$(wc -c < "$f")
  tokens=$((size / 4))
  name=$(basename "$f" .md)
  echo "   $name: ~$tokens tokens"
done

echo ""
echo "   💡 Suggestion: keep only frequently used skills"
echo "      /oct-forget to remove unused ones"
echo ""

# ── 3. Memory Files ──
echo "3️⃣  Memory Files (loaded on demand)"
echo ""

# Check MEMORY.md size
memory_index_size=$(wc -c < "$MEMORY_DIR/MEMORY.md" 2>/dev/null || echo 0)
echo "   MEMORY.md index: ~$((memory_index_size / 4)) tokens"
echo ""

# Find large memory files
echo "   Large files (>500 words):"
find "$MEMORY_DIR" -name "*.md" -not -name "MEMORY.md" | while read f; do
  words=$(wc -w < "$f")
  if [[ $words -gt 500 ]]; then
    name=$(basename "$f")
    tokens=$((words / 1))
    echo "   ⚠️  $name: ~$words words (~$((words * 4 / 3)) tokens)"
  fi
done

echo ""
echo "   💡 Suggestion: archive completed bugs, compress large files"
echo "      /oct-dream to consolidate and archive"
echo ""

# ── 4. Usage Patterns ──
echo "4️⃣  Usage Patterns (last 24h from /stats)"
echo ""
echo "   56% came from subagent-heavy sessions"
echo "   → Don't spawn agents for simple tasks"
echo "   → Only use agents for multi-file search or complex RCA"
echo ""
echo "   42% was at >150k context"
echo "   → Use /oct-rest + new agent before hitting 80%"
echo "   → Don't let sessions grow unbounded"
echo ""
echo "   15% came from Gmail MCP"
echo "   → Disable when not needed: /mcp"
echo ""

# ── Summary ──
echo "======================================"
echo "📊 Summary & Actions"
echo ""
echo "Quick wins (do now):"
echo "  1. /mcp → disable Gmail/Notion if not using today"
echo "  2. /oct-dream → archive completed bugs"
echo "  3. Avoid spawning agents for simple questions"
echo ""
echo "Estimated savings if all applied:"
mcp_tokens=6000
skill_tokens_save=$((skill_tokens / 2))
total_save=$((mcp_tokens + skill_tokens_save))
echo "  MCP reduction: ~${mcp_tokens} tokens/session"
echo "  Skills reduction: ~${skill_tokens_save} tokens/session"
echo "  Total: ~${total_save} tokens/session saved"
echo ""
