#!/bin/bash
# Auto-merge related memory files with state tracking

MEMORY_DIR="$HOME/.claude/projects/-home-alonso/memory"
BACKUP_DIR="$MEMORY_DIR/archive/merged-$(date +%Y%m%d)"
MERGE_TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")

mkdir -p "$BACKUP_DIR"

echo "🌙 Memory Auto-Merger"
echo ""
echo "Scanning for related files to merge..."
echo ""

# Function to check if merge is needed
needs_merge() {
  local merged_file=$1
  local source_files=("${@:2}")
  
  # If merged file doesn't exist, always merge
  if [[ ! -f "$merged_file" ]]; then
    return 0
  fi
  
  # Check if any source file is newer than merged file
  local merged_mtime=$(stat -f%m "$merged_file" 2>/dev/null || stat -c%Y "$merged_file" 2>/dev/null)
  
  for src_file in "${source_files[@]}"; do
    local src_path="$MEMORY_DIR/$src_file"
    if [[ -f "$src_path" ]]; then
      local src_mtime=$(stat -f%m "$src_path" 2>/dev/null || stat -c%Y "$src_path" 2>/dev/null)
      if [[ $src_mtime -gt $merged_mtime ]]; then
        return 0  # Source file is newer
      fi
    fi
  done
  
  return 1  # No merge needed
}

# Function to get file modification date
get_file_date() {
  local file=$1
  if [[ -f "$file" ]]; then
    stat -f%Sm -t "%Y-%m-%d" "$file" 2>/dev/null || stat -c%y "$file" 2>/dev/null | cut -d' ' -f1
  else
    echo "unknown"
  fi
}

# Function to merge related files
merge_task() {
  local prefix=$1  # e.g., "sys1821"
  local title=$2   # e.g., "SYS-1821: MLO FT Roaming Issues"
  
  local files=()
  local merged_file="$MEMORY_DIR/${prefix}-complete.md"
  
  # Find all files with this prefix
  mapfile -t files < <(ls "$MEMORY_DIR" | grep -i "^${prefix}" | grep "\.md$")
  
  if [[ ${#files[@]} -gt 1 ]]; then
    if ! needs_merge "$merged_file" "${files[@]}"; then
      echo "✓ $prefix: Already consolidated (no changes)"
      return 1
    fi
    
    echo "📝 Merging ${#files[@]} files for $prefix..."
    
    # Backup originals
    for f in "${files[@]}"; do
      cp "$MEMORY_DIR/$f" "$BACKUP_DIR/"
    done
    
    # Build source file list for metadata
    local source_list=""
    for f in "${files[@]}"; do
      local mod_date=$(get_file_date "$MEMORY_DIR/$f")
      source_list+="  - $f (modified: $mod_date)"$'\n'
    done
    
    # Create merged file with metadata
    {
      echo "---"
      echo "consolidated: true"
      echo "merged-at: $MERGE_TIMESTAMP"
      echo "source-files:"
      echo "$source_list" | sed 's/^/  /'
      echo "status: up-to-date"
      echo "---"
      echo ""
      echo "# $title"
      echo ""
      
      # Add each file's content as a section
      for f in "${files[@]}"; do
        section_name=$(echo "$f" | sed "s/^${prefix}_//; s/^${prefix}-//; s/\.md$//" | tr '_' ' ' | sed 's/\b\(.\)/\u\1/g')
        echo "## $section_name"
        echo ""
        tail -n +2 "$MEMORY_DIR/$f" 2>/dev/null  # Skip first line (title)
        echo ""
        echo "---"
        echo ""
      done
    } > "$merged_file"
    
    echo "  ✓ Merged into: ${prefix}-complete.md"
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
SKIPPED_COUNT=0

for task in "${TASKS[@]}"; do
  IFS=':' read -r prefix title <<< "$task"
  if merge_task "$prefix" "$title"; then
    ((MERGED_COUNT++))
  else
    if [[ -f "$MEMORY_DIR/${prefix}-complete.md" ]]; then
      ((SKIPPED_COUNT++))
    fi
  fi
done

echo ""
echo "📊 Consolidation Summary:"
echo "  Newly merged: $MERGED_COUNT"
echo "  Already consolidated: $SKIPPED_COUNT"
echo "  Backups saved to: archive/merged-$(date +%Y%m%d)/"
echo ""
echo "✨ Memory organized and tracked!"
echo ""
echo "Next: /oct-dream to continue organizing memories"
