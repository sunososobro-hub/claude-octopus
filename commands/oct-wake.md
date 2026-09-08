# oct-wake

One-shot handoff: resume work from the latest `/oct-save` checkpoint instead
of `claude --resume`-ing a whole old session back into context.

## Usage

```bash
/oct-wake              # Load the latest unconsumed checkpoint
/oct-wake <hash>        # Load a specific checkpoint by its 8-char hash
/oct-wake --list        # List recent checkpoints without loading one
/oct-wake --list all    # List everything — active + archived, dream-organized
/oct-wake <keyword>     # Search checkpoints by topic (e.g. "gmail", "元寶")
```

## Why this exists

`claude --resume` reattaches the entire old session — everything you said,
everything Claude read, all of it, still occupying context on every future
turn. `/oct-save` already writes a ~1-2k token checkpoint for exactly this
situation; `/oct-wake` is the other half — load *that*, not the whole
session, into a fresh one.

## Step 1 — Find the checkpoint(s)

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
- If the user passed a specific hash: use that file (check both active and
  archived locations).
- If the user passed anything else that isn't a flag or a hash — a
  keyword, a project name, a natural-language phrase (e.g. "gmail",
  "元寶", "幫我找 wifi 那個"): search both active **and archived**
  checkpoints (task line + content, not just the title — an archived
  checkpoint is decluttered, not gone) for matches. Show a numbered list
  (hash, date, task line) same style as `/oct-recall`'s search, and ask
  which to load. Never guess which one from a search match — always
  confirm, even if there's only one hit.
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

If there are no checkpoint files at all, say so and suggest `/oct-save` next
time before clearing — don't fabricate one.

## Step 2 — Load it

Read the checkpoint file (it's small, ~1-2k tokens — that's the whole
point). Do **not** also go read the original session's transcript or try to
reconstruct more than what's in the checkpoint.

If the checkpoint's `## 相關記憶檔案` section lists memory files, do **not**
auto-load them. List them like `/oct-recall` does and ask which ones (if
any) are worth pulling in now. Auto-loading everything defeats the purpose —
most of the value here is in NOT dragging in more than you need.

## Step 3 — Mark it consumed

Write the loaded checkpoint's hash to `~/.claude/summaries/.last_woken`
(plain text, just the hash) so the SessionStart nudge (see `oct-wake`
hook wiring in `oct-watch.md`'s sibling setup) stops reminding about a
checkpoint that's already been picked up.

```bash
echo "<hash>" > ~/.claude/summaries/.last_woken
```

## Step 4 — Confirm

```
✅ Woke from a1b2c3d4 (2026-08-20 10:45)
任務: [one-line summary from ## 任務 or ## Task, whichever is present]
下一步: [first item from ## 下一步 or ## Next Steps, whichever is present]
```

Do not print the full checkpoint content again — the user just read it in
Step 2's tool output; repeating it verbatim wastes output tokens.
