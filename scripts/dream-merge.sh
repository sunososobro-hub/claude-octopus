#!/bin/bash
# Auto-merge related memory files into unified task records

MEMORY_DIR="$HOME/.claude/projects/-home-alonso/memory"
BACKUP_DIR="$MEMORY_DIR/archive/merged-$(date +%Y%m%d)"

mkdir -p "$BACKUP_DIR"

echo "🌙 Memory Auto-Merger"
echo ""
echo "Scanning for related files to merge..."
echo ""

# Function to merge related files
merge_task() {
  local prefix=$1  # e.g., "sys1821"
  local title=$2   # e.g., "SYS-1821: MLO FT Roaming Issues"
  
  local files=()
  local merged_file="$MEMORY_DIR/${prefix}-complete.md"
  
  # Find all files with this prefix
  mapfile -t files < <(ls "$MEMORY_DIR" | grep -i "^${prefix}" | grep "\.md$")
  
  if [[ ${#files[@]} -gt 1 ]]; then
    echo "Found ${#files[@]} related files for $prefix:"
    
    # Backup originals
    for f in "${files[@]}"; do
      cp "$MEMORY_DIR/$f" "$BACKUP_DIR/"
      echo "  - $f"
    done
    
    # Create merged file
    {
      echo "# $title"
      echo ""
      
      # Add each file's content as a section
      for f in "${files[@]}"; do
        section_name=$(echo "$f" | sed "s/^${prefix}_//; s/\.md$//" | tr '_' ' ' | sed 's/\b\(.\)/\u\1/g')
        echo "## $section_name"
        echo ""
        tail -n +2 "$MEMORY_DIR/$f" 2>/dev/null  # Skip first line (title)
        echo ""
        echo "---"
        echo ""
      done
    } > "$merged_file"
    
    echo "  ✓ Merged into: ${prefix}-complete.md"
    echo ""
    return 0
  fi
  return 1
}

# Detect and merge task groups
declare -a TASKS=(
  "sys1821:SYS-1821: MLO FT Roaming Issues"
  "sys1859:SYS-1859: Site-Survey Hang (30s)"
  "sys1844:SYS-1844: iPhone Reconnect PMKID"
  "sys1811:SYS-1811: MT7993 BTM UAF"
  "sys1796:SYS-1796: OWE APCli PMKID"
  "sys1764:SYS-1764: Cross-band FT"
)

MERGED_COUNT=0
for task in "${TASKS[@]}"; do
  IFS=':' read -r prefix title <<< "$task"
  if merge_task "$prefix" "$title"; then
    ((MERGED_COUNT++))
  fi
done

echo "📊 Merge Summary:"
echo "  Tasks merged: $MERGED_COUNT"
echo "  Backups saved to: archive/merged-$(date +%Y%m%d)/"
echo ""
echo "✨ Memory now consolidated into unified task files!"
