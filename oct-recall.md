# oct-recall

Load memory files into current session context. Category-based browsing.

## Usage

```bash
/oct-recall              # Show categories
/oct-recall <category>   # Show items in a category
/oct-recall <keyword>    # Search across all memories
```

## CRITICAL: Do NOT read any memory files until the user explicitly selects them.

## Step 1 — Show Categories

Read ONLY `~/.claude/projects/-home-alonso/memory/MEMORY.md` (the index file).
Count items under each `##` section. Show the list. Then STOP and wait for user input.
Do NOT read any individual memory .md files at this step.

```
🧠 oct-recall — Memories

  1  🐛 Bug Investigations    (8)
  2  🏗️ Architecture Patterns  (2)
  3  🛠️ Tools                  (2)
  4  📖 SOPs                   (3)
  5  🖥️ Environment            (5)
  6  📚 Reference              (3)
  7  💬 Feedback               (4)

Pick category (e.g. "1"), or search (e.g. "FT roaming"):
```

**STOP. Wait for user response before doing anything else.**

## Step 2 — Show Category Items

After user picks a category number, list its items from MEMORY.md. Then STOP.
Do NOT read any memory files yet.

```
🐛 Bug Investigations

  1  SYS-1796 OWE APCli PMKID
  2  SYS-1811 mt7993 BTM UAF
  3  SYS-1821 MLO FT Roaming
  ...

Load which? (e.g. "3 7", "all", or "b" to go back)
```

**STOP. Wait for user to specify which items to load.**

## Step 3 — Load Selected Memories

ONLY after user specifies items: read the selected `.md` files and output their content.

Confirm: `✅ Loaded: SYS-1821, 5.1.0 MWS Regression`

## Search

If user types a keyword, partial name, or natural language query (e.g. "FT roaming", "幫我找 XX 相關", "/ keyword"), scan all MEMORY.md entries for matches and show a flat numbered list to pick from:

```
🔍 "FT roaming" 相關

  1  SYS-1821 MLO FT Roaming
  2  SYS-1821 MLO FT Roaming Debug
  3  SYS-1764 Cross-band FT

Load which? (e.g. "1 2")
```
