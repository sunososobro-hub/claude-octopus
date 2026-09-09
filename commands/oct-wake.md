---
description: 醒來：讀便條接著做（取代 claude --resume）；<關鍵字> 同時搜便條+長期記憶；--memory 翻記憶目錄
---

# oct-wake

One-shot handoff: resume work from the latest `/oct-nap` checkpoint instead
of `claude --resume`-ing a whole old session back into context. Also the
single entry point for pulling anything out of long-term memory.

## Usage

```bash
/oct-wake              # Load the latest unconsumed checkpoint
/oct-wake <hash>        # Load a specific checkpoint by its 8-char hash
/oct-wake --list        # List recent checkpoints without loading one
/oct-wake --list all    # List everything — active + archived, dream-organized
/oct-wake --memory      # List long-term memory index, pick what to load
/oct-wake <keyword>     # Search checkpoints AND long-term memory (e.g. "gmail", "1013")
```

## Why this exists

`claude --resume` reattaches the entire old session — everything you said,
everything Claude read, all of it, still occupying context on every future
turn. `/oct-nap` already writes a ~1-2k token checkpoint for exactly this
situation; `/oct-wake` is the other half — load *that*, not the whole
session, into a fresh one.

Two pools, one command:

- **Checkpoints** (`~/.claude/summaries/`) — "what was I doing": one per
  task, written by `/oct-nap`, meant to be resumed.
- **Long-term memory** (the project's `memory/` directory) — "what have I
  learned": curated notes that outlive any single task.

Users shouldn't have to know which pool a thing lives in. A keyword search
scans both; `--memory` browses the second on its own.

## Where long-term memory lives

The directory named in the auto-memory section of your system prompt:
`~/.claude/projects/<slug>/memory/`, where `<slug>` is the current working
directory with every `/` replaced by `-` (e.g. `/home/me/proj` →
`-home-me-proj`). `MEMORY.md` there is the index — one line per memory file
with a description. **Read only the index to list or search; never read
the individual memory files until the user picks them.**

## Step 1 — Find it

List `~/.claude/summaries/*.md` (exclude `.last_woken` and the `archive/`
subdirectory), sorted by mtime (newest first). The "task" line for each
comes from whichever heading is present — checkpoints aren't all written
with the same header language, so check both `## 任務` and `## Task` (and
similarly `## 下一步`/`## Next Steps` later in Step 4) rather than assuming
one.

- **`--list` (no `all`)**: show only the **5 most recent** active
  checkpoints (hash, date, task line). If there are more, add a line like
  `...還有 N 個更舊的，用 --list all 看全部`. STOP — do not load anything.
- **`--list all`**: show everything in two sections — **進行中**
  (everything found above, not just the 5) and **已歸檔**
  (`~/.claude/summaries/archive/*.md`, if that directory exists — these
  are checkpoints `/oct-dream`'s sweep judged done; see `oct-dream.md`).
  STOP — do not load anything.
- **`--memory`**: read `MEMORY.md` only. Show its entries as a numbered
  list (name + description). Ask which to load. STOP until the user picks.
- If the user passed a specific hash: use that file (check both active and
  archived locations).
- If the user passed anything else that isn't a flag or a hash — a
  keyword, a project name, a natural-language phrase (e.g. "gmail",
  "1013", "幫我找 wifi 那個"): search **three places** — active
  checkpoints, archived checkpoints (task line + content; an archived
  checkpoint is decluttered, not gone), and `MEMORY.md` index lines. Show
  one numbered list, each hit tagged with where it came from:

  ```
  🔍 "staging" 相關

    1  便條  2fb2c489  2026-09-08  Staging DB 遷移 / 連線設定
    2  筆記  staging_db_migration — staging 環境的 migration 步驟與已知坑
    3  筆記  service_credentials — 各環境的登入方式索引

  Load which? (e.g. "1", "2 3")
  ```

  Never guess which one from a search match — always confirm, even if
  there's only one hit.
- Otherwise (no flags): count the active checkpoints.
  - **Exactly one** → load it directly, no need to ask.
  - **More than one** → list them (numbered, hash, date, task line) and
    ask which to load. This applies regardless of `.last_woken` —
    "newest" is not the same as "the one you want to resume in this new
    window." If you have several pieces of work in flight (multiple
    projects, multiple windows each saved separately), opening a new
    session doesn't tell you which one the user means to continue;
    guessing "most recent" is exactly the wrong default when the whole
    point of asking is that recency isn't relevance. `.last_woken` still
    drives the SessionStart nudge (unconsumed-checkpoint reminder) — it's
    just not the gate for whether `/oct-wake` asks here.

If there are no checkpoint files at all, say so and suggest `/oct-nap` next
time before clearing — don't fabricate one.

## Step 2 — Load it

**Checkpoint**: read the file (it's small, ~1-2k tokens — that's the whole
point). Do **not** also go read the original session's transcript or try to
reconstruct more than what's in the checkpoint.

If the checkpoint's `## 相關記憶檔案` / `## Related Memory Files` section
lists memory files, do **not** auto-load them. List them (name + the
one-line description from `MEMORY.md`) and ask which ones (if any) are
worth pulling in now. Auto-loading everything defeats the purpose — most of
the value here is in NOT dragging in more than you need.

**Memory file**: read the selected `.md` files. Do **not** print their
content back — it's already in context, echoing it just doubles the output
tokens. Confirm only: `✅ Loaded: staging_db_migration, service_credentials`

## Step 3 — Mark it consumed (checkpoints only)

Write the loaded checkpoint's hash to `~/.claude/summaries/.last_woken`
(plain text, just the hash) so the SessionStart nudge (see `oct-wake`
hook wiring in `oct-pulse.md`'s sibling setup) stops reminding about a
checkpoint that's already been picked up.

```bash
echo "<hash>" > ~/.claude/summaries/.last_woken
```

Skip this step if only memory files were loaded — there's nothing to
consume.

## Step 4 — Confirm

```
✅ Woke from a1b2c3d4 (2026-08-20 10:45)
任務: [one-line summary from ## 任務 or ## Task, whichever is present]
下一步: [first item from ## 下一步 or ## Next Steps, whichever is present]
```

Do not print the full checkpoint content again — the user just read it in
Step 2's tool output; repeating it verbatim wastes output tokens.
