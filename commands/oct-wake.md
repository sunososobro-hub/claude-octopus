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
- Otherwise (no flags): count the active checkpoints, then cluster them by
  project the same way as the grouping rules below.
  - **Exactly one checkpoint total** → load it directly, no need to ask.
  - **One cluster only** (several checkpoints, all one project) → list that
    cluster's checkpoints (numbered, hash, date, task line) and ask which
    to load — there's nothing to collapse, the user is already at the
    project they mean.
  - **More than one cluster** → drill down in two steps instead of
    dumping every checkpoint at once. First show only the cluster names
    (count + most recent date each), nothing else:

    ```
    你有 3 個進行中的專案：

      1  SYS-1883（RADIUS Accounting）   3 張，最新 2026-09-09 17:07
      2  YuanBaoBudget / AriBao          3 張，最新 2026-09-09 17:07
      3  RD Auto Sanity System           1 張，最新 2026-09-09 17:00

    要接續哪個專案？
    ```

    Once the user picks a cluster:
    - **Only one checkpoint** in it → load it directly, no further ask.
    - **More than one checkpoint** → these aren't independent options to
      choose between, they're successive snapshots of the same ongoing
      task (like SYS-1883's three checkpoints, each superseding the last).
      Don't list them for a pick — read all of them and synthesize one
      consolidated todo view instead, and go straight to a yes/no continue
      prompt rather than a numbered choice:

      ```
      📋 SYS-1883（RADIUS Accounting） — 3 張便條合併（最新 b4e1c920, 2026-09-09 17:07）

      目前狀況：[latest checkpoint's ## Task, one line]

      ✅ 已完成 3 項（輸入「展開」查看）

      Todo
      - [ ] [the latest checkpoint's own still-open Next Steps items,
             oldest-written first]

      要接續嗎？
      ```

      Only show the still-open `[ ]` items by default — collapse everything
      already marked/inferred done into that one `✅ 已完成 N 項` count line,
      not a printed list. This matters more as a cluster accumulates more
      checkpoints over time: a long list of finished items is exactly the
      noise this drill-down exists to avoid. Expand the done items into a
      real `- [x]` list only if the user explicitly asks (e.g. "展開",
      "完成的是什麼").

      Synthesis rule: walk the cluster oldest → newest. Carry forward each
      checkpoint's `## Next Steps` items; when a later checkpoint's Task or
      Key Findings shows an earlier item was finished, count it toward the
      done total instead of repeating it as still-open — don't just
      concatenate all checkpoints' lists verbatim, that defeats the point.
      Use the latest checkpoint's own Task line as "目前狀況" (it's the most
      current framing of the work). If the checkpoints genuinely describe
      unrelated sub-threads within the same project (not a linear
      progression), say so instead of forcing a fake merge, and fall back
      to listing them numbered.

      On "要接續嗎" yes: proceed to Step 2 using the **latest** checkpoint
      in the cluster as the one that gets read/marked-consumed in Step 3
      (the older ones' content is already folded into the todo view above,
      so there's nothing left to re-read from them). Mention once, briefly,
      that the older checkpoints in this cluster look superseded and
      `/oct-dream` would archive them — don't do it yourself, just note it.

  This two-step drill-down applies only to the bare no-flag call — it's the
  "I don't want to see much" default. `--list` and `--list all` are the
  explicit "show me everything" escape hatches and stay flat/full as
  described above. This applies regardless of `.last_woken` — "newest" is
  not the same as "the one you want to resume in this new window." If you
  have several pieces of work in flight (multiple projects, multiple
  windows each saved separately), opening a new session doesn't tell you
  which one the user means to continue; guessing "most recent" is exactly
  the wrong default when the whole point of asking is that recency isn't
  relevance. `.last_woken` still drives the SessionStart nudge
  (unconsumed-checkpoint reminder) — it's just not the gate for whether
  `/oct-wake` asks here.

If there are no checkpoint files at all, say so and suggest `/oct-nap` next
time before clearing — don't fabricate one.

### Grouping when listing multiple checkpoints

This is the shared clustering rule referenced above by both the no-flag
drill-down and the flat `--list`/`--list all` output — checkpoints pile up
faster than `/oct-dream` runs, so don't ever dump them as one flat
chronological list once there's more than a couple. Cluster by underlying
project/ticket first, inferred
from the task line (a ticket ID like SYS-XXXX, a repo/app name, a
recognizable initiative name). Sort clusters by their most recent checkpoint
(newest cluster first); within a cluster, newest first, numbered from 1
locally per cluster — not continuously across the whole list. A checkpoint
that shares no project with any other gets its own single-item cluster
rather than being forced into one. Archived checkpoints in `--list all`'s
已歸檔 section stay a flat list — `/oct-dream` already declutters those.

```
📋 進行中的便條

SYS-1883（RADIUS Accounting）
  1  b4e1c920  2026-09-09 17:07  review rt2860apd 3 個既有 commit，砍 AI 味長篇註解
  2  6daa928a  2026-09-09 13:08  mt7916_ap.ko + rt2860apd 裝 KN-1012 實機測試
  3  15fcdfc0  2026-09-09 12:19  KN-1012 連線問題（較舊，可能已過時）

RD Auto Sanity System
  1  47b882b6  2026-09-09 17:00  WireGuard VPN 驗證成功，延伸 8-repo 提案草稿

YuanBaoBudget / AriBao
  1  a3c58d2f  2026-09-09 17:07  視覺設計整理案
  2  1da10601  2026-09-09 13:08  運動計時器/備份系統/照片支援
  3  92ba3e8a  2026-09-08 23:25  adb 配對腳本 + Android CI 串接
```

Numbers repeat across clusters (each restarts at 1), so ask the user to pick
by hash when it's ambiguous, or accept "cluster name + number" (e.g. "1883
#2") as equivalent to a hash.

### Due dates

Most checkpoints won't have a `## Due` section — that's normal, leave their
ordering exactly as above. When one does:

- Show a badge after its task line: `📅 2026-09-15` for a date, or the
  urgency phrase as written (e.g. `⏰ 這個很急`) when it wasn't a date. If a
  dated one is in the past, use `⚠️` instead of `📅`.
- Within a cluster, due checkpoints float to the top, soonest-due first,
  ahead of the normal newest-first ordering — non-dated urgency phrases
  (no comparable date) go above dated ones, since "soonest" can't be
  computed for them.
- A cluster containing any due checkpoint sorts ahead of clusters that
  don't, regardless of the newest-cluster-first rule.

```
📋 進行中的便條

SYS-1883（RADIUS Accounting）
  1  b4e1c920  2026-09-09 17:07  ⚠️ 2026-09-08  review rt2860apd 3 個既有 commit...
  2  6daa928a  2026-09-09 13:08  mt7916_ap.ko + rt2860apd 裝 KN-1012 實機測試
  3  15fcdfc0  2026-09-09 12:19  KN-1012 連線問題（較舊，可能已過時）
```

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
[📅/⚠️ Due line, only if the checkpoint has a ## Due section]
下一步:
- [ ] [each item from ## 下一步 or ## Next Steps, as written — including any already checked [x]]
```

Print the whole `## Next Steps` checklist here, not just the first item —
it's already short by construction, and showing all of it is what makes it
useful as a todo list across wake/nap cycles instead of a single reminder
line. Still do not print the full checkpoint content again — Key
Findings/Important Context were already read in Step 2's tool output;
repeating those verbatim wastes output tokens.
