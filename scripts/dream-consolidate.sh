#!/bin/bash
# Memory consolidation analyzer

MEMORY_DIR="$HOME/.claude/projects/-home-alonso/memory"

if [[ ! -d "$MEMORY_DIR" ]]; then
  echo "❌ Memory directory not found"
  exit 1
fi

echo "🌙 Memory Consolidation Analyzer"
echo ""

# Count files
TOTAL_FILES=$(find "$MEMORY_DIR" -type f -name "*.md" | wc -l)
MEMORY_SIZE=$(du -sh "$MEMORY_DIR" 2>/dev/null | cut -f1)

echo "Current state:"
echo "  Total files: $TOTAL_FILES"
echo "  Total size: $MEMORY_SIZE"
echo ""

# Analyze by type
echo "Files by type:"
echo "  Feedback: $(find "$MEMORY_DIR" -name "feedback_*.md" | wc -l)"
echo "  SOP: $(find "$MEMORY_DIR" -name "sop_*.md" | wc -l)"
echo "  Bug summaries: $(find "$MEMORY_DIR" -name "sys*.md" | wc -l)"
echo "  Reference: $(find "$MEMORY_DIR" -name "*reference*.md" -o -name "*mapping*.md" | wc -l)"
echo "  Notes: $(find "$MEMORY_DIR" -name "*_*.md" -not -name "MEMORY.md" | wc -l)"
echo ""

# Suggest organization
echo "📊 Organization Suggestions:"
echo ""
echo "1️⃣ By Category (Current rough state):"
echo "  memory/"
echo "  ├─ feedback/ (preferences & style)"
echo "  ├─ sops/ (standard operating procedures)"
echo "  ├─ bugs/ (issue tracking summaries)"
echo "  ├─ reference/ (external resources)"
echo "  └─ archive/ (completed items)"
echo ""

echo "2️⃣ By Task:"
echo "  memory/"
echo "  ├─ tasks/SYS-1859/"
echo "  ├─ tasks/SYS-1844/"
echo "  ├─ tasks/SYS-1821/"
echo "  ├─ reference/ (shared)"
echo "  └─ feedback/ (shared)"
echo ""

echo "3️⃣ By Priority:"
echo "  memory/"
echo "  ├─ active/ (current work)"
echo "  ├─ reference/ (guides & patterns)"
echo "  └─ archive/ (completed)"
echo ""

echo "Run:"
echo "  /oct-dream        to start organization"
echo "  /oct-dream --help for more options"
