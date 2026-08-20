List available session summaries and let the user pick which to load.

Steps:

1. Run this to list summaries:
```bash
ls -t ~/.claude/summaries/*.md 2>/dev/null | while read f; do
  hash=$(basename "$f" .md)
  header=$(head -1 "$f" | sed 's/^# //')
  task=$(grep -A1 "^## Task" "$f" | tail -1 | cut -c1-50)
  printf "%s  |  %s\n" "$header" "$task"
done
```

2. Show last 5 by default:

```
Available summaries (showing last 5 — type 'all' to see more):

  1. a1b2c3d4 | 2026-08-20 16:00  —  Debugging MT7927 wifi driver
  2. e5f6a7b8 | 2026-08-19 22:30  —  SYS-1859 scan fix verification
  3. ...
```

3. Ask: "Which to load? Enter number(s) (e.g. `1` or `1 3`) or `all` to see full list:"

4. If `all`: re-run step 1 without limit, then let user pick.

5. Read the selected `~/.claude/summaries/{hash}.md` files and present the content, then say "Loaded — ready to continue."
