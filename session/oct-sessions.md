Parse the argument `$ARGUMENTS` and run this bash command:

```bash
PROJ_DIR="$HOME/.claude/projects/$(echo "$HOME" | sed 's|/|-|g')"

declare -A HAS_SUMMARY
while IFS= read -r f; do
  hash=$(basename "$f" .md | sed "s/session_//")
  HAS_SUMMARY["$hash"]=1
done < <(ls "$PROJ_DIR/memory/session_*.md" 2>/dev/null)

ROWS=()
for f in "$PROJ_DIR"/*.jsonl; do
  [ -f "$f" ] || continue
  hash=$(basename "$f" .jsonl | cut -c1-8)
  fdate=$(date -r "$f" "+%Y-%m-%d")
  mtime=$(date -r "$f" "+%s")
  first_msg=$(grep -m1 '"role"' "$f" 2>/dev/null | python3 -c "
import sys, json
try:
    obj = json.loads(sys.stdin.read())
    msg = obj.get('message', {})
    if msg.get('role') != 'user':
        print('(unreadable)')
        sys.exit()
    content = msg.get('content', '')
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get('type') == 'text':
                print(c['text'][:65].replace('\n',' '))
                break
    elif isinstance(content, str):
        print(content[:65].replace('\n',' '))
except:
    print('(unreadable)')
" 2>/dev/null)
  tag=""
  [ "${HAS_SUMMARY[$hash]+_}" ] && tag=" ★"
  ROWS+=("$mtime|$fdate|$hash|$first_msg$tag")
done

IFS=$'\n' SORTED=($(printf '%s\n' "${ROWS[@]}" | sort -t'|' -k1,1n))
unset IFS

ARGS="$ARGUMENTS"
TODAY=$(date "+%Y-%m-%d")

if [[ "$ARGS" == "all" ]]; then
  FILTER="all"
elif [[ "$ARGS" =~ ^-n[[:space:]]+([0-9]+)$ ]]; then
  FILTER="last"; N="${BASH_REMATCH[1]}"
elif [[ "$ARGS" =~ ^([0-9]+)$ ]]; then
  FILTER="last"; N="${BASH_REMATCH[1]}"
elif [[ "$ARGS" == "yesterday" || "$ARGS" == "-1" ]]; then
  FILTER="day"; TARGET=$(date -d "yesterday" "+%Y-%m-%d")
elif [[ "$ARGS" =~ ^-([0-9]+)$ ]]; then
  FILTER="day"; TARGET=$(date -d "${BASH_REMATCH[1]} days ago" "+%Y-%m-%d")
else
  FILTER="recent"
  D1=$(date -d "yesterday" "+%Y-%m-%d")
  D2="$TODAY"
fi

prev_date=""

print_row() {
  local fdate="$1" hash="$2" msg="$3"
  if [[ "$fdate" != "$prev_date" ]]; then
    echo ""
    echo "### $fdate"
    prev_date="$fdate"
  fi
  printf "  \`%s\`  %s\n" "$hash" "$msg"
}

if [[ "$FILTER" == "last" ]]; then
  START=$(( ${#SORTED[@]} - N ))
  [ $START -lt 0 ] && START=0
  for row in "${SORTED[@]:$START}"; do
    IFS='|' read -r _ fdate hash msg <<< "$row"
    print_row "$fdate" "$hash" "$msg"
  done
else
  for row in "${SORTED[@]}"; do
    IFS='|' read -r _ fdate hash msg <<< "$row"
    show=0
    case "$FILTER" in
      all)    show=1 ;;
      day)    [[ "$fdate" == "$TARGET" ]] && show=1 ;;
      recent) [[ "$fdate" == "$D1" || "$fdate" == "$D2" ]] && show=1 ;;
    esac
    [ $show -eq 0 ] && continue
    print_row "$fdate" "$hash" "$msg"
  done
fi

echo ""
echo "★ = has summary file"
```

Display the output as-is. Supported args: `yesterday`/`-1`, `-2`, `-3`…, `5` or `-n 5` (last N), `all`.
Default (no arg) = today + yesterday.
