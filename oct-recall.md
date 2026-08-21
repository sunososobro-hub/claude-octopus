# oct-recall

Load memory files into current session context. Category-based browsing.

## Usage

```bash
/oct-recall              # Show categories
/oct-recall <category>   # Show items in a category
/oct-recall <keyword>    # Search across all memories
```

## Step 1 — Show Categories

Read `~/.claude/projects/-home-alonso/memory/MEMORY.md`. List the `##` sections with item count:

```
🧠 oct-recall — Memories

  1  🐛 Bug Investigations    (8)
  2  🏗️ Architecture Patterns  (2)
  3  🛠️ Tools                  (2)
  4  📖 SOPs                   (3)
  5  🖥️ Environment            (5)
  6  📚 Reference              (3)
  7  💬 Feedback               (4)

Pick category (e.g. "1"), search ("/ keyword"), or load by name:
```

## Step 2 — Show Category Items

After user picks a category, list its items numbered:

```
🐛 Bug Investigations

  1  SYS-1796 OWE APCli PMKID
  2  SYS-1811 mt7993 BTM UAF
  3  SYS-1821 MLO FT Roaming
  4  SYS-1821 MLO FT Roaming Debug
  5  SYS-1844 iPhone Reconnect
  6  SYS-1859 Site-survey 卡30s
  7  SYS-1764 Cross-band FT
  8  5.1.0 MWS Regression

Load which? (e.g. "3 7", "all", or "b" to go back)
```

## Step 3 — Load Selected Memories

Read the selected `.md` files from `~/.claude/projects/-home-alonso/memory/` and output their full content into context.

Confirm: `✅ Loaded: SYS-1821, 5.1.0 MWS Regression`

Memories stack — user can repeat to load from multiple categories.

## Search

If user types a keyword, partial name, or natural language query (e.g. "FT roaming", "幫我找 XX 相關", "/ keyword"), scan all MEMORY.md entries for matches and show a flat numbered list to pick from:

```
🔍 "FT roaming" 相關

  1  SYS-1821 MLO FT Roaming
  2  SYS-1821 MLO FT Roaming Debug
  3  SYS-1764 Cross-band FT

Load which? (e.g. "1 2")
```
