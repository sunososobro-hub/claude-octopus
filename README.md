# oct-toolkit

Token-frugal session memory and usage tracking for Claude Code.

## When to use it

Short version: it makes Claude Code remember things the way a person would,
without getting more expensive the longer you use it.

- **Starting work for the day** → `/oct-wake`: picks up yesterday's note
  instead of re-reading the whole old conversation (which costs a lot more).
- **Mid-task, context getting fat, or stepping away for a bit** →
  `/oct-nap`, then `/clear`: writes a ~1-2k word note, clears, `/oct-wake`
  picks it back up next time.
- **"Didn't I run into this before?"** → `/oct-wake <keyword>`: searches
  checkpoints and long-term memory together — no need to remember which
  pool something lives in.
- **Wrapping up for the day** → `/oct-sleep`: writes the note and
  consolidates memory in one shot. In a multi-window day, run this only in
  the last window you close; the others just `/oct-nap`.
- **Wondering what you've spent** → the status bar (turned on by
  `/oct-pulse`) shows it live; for a detailed breakdown, or to check
  whether you have any wasteful habits, use `/oct-checkup`.

The rest of this doc is for anyone who wants the details, or is picking
this up to maintain.

## Why

`claude --resume` reattaches a whole old session — every message, every file
read, still sitting in context on every future turn. This toolkit's core bet
is that **curated, selective recall beats automatic full-context reload**:
save a small handoff note, start clean, load only what's actually relevant.

This is a deliberate contrast to auto-capture-everything memory tools. Those
are convenient, but real users report they can *increase* token usage (the
compression/injection steps aren't free, and automatic relevance-guessing
over-injects). Nothing here loads automatically except a one-line "you have
a pending checkpoint" nudge — everything else is loaded on request.

## Does it actually save tokens?

Task type, session length, and model all change the ratio, so don't take
anyone else's number as a guarantee for your own setup. Check it yourself,
with one command:

```
/oct-checkup --current
```

Run it right before you'd normally `/oct-nap` (context feels fat) to get
**Before**. Then `/oct-nap` → `/clear` → `/oct-wake`, and run it again in
the new session to get **After**. The gap between the two is your real
saving, for your own workload.

For reference, here's what that comparison actually looked like on my
machine — 8 real past sessions, resumed for real (`claude --resume`) vs.
loaded via `/oct-wake` with one fixed checkpoint, same model pinned for
both sides so the comparison isn't skewed by an unrelated cache miss:

| Old session size | `--resume` tokens | `--resume` cost | `/oct-wake` tokens | `/oct-wake` cost | Cost saved |
|---|---|---|---|---|---|
| 21K | 21,326 | $0.0880 | 25,569 | $0.0610 | 31% |
| 26K | 25,966 | $0.0616 | 25,848 | $0.0514 | 17% |
| 37K | 36,532 | $0.1030 | 28,310 | $0.0642 | 38% |
| 62K | 61,713 | $0.1971 | 25,620 | $0.0481 | 76% |
| 72K | 71,735 | $0.2738 | 27,887 | $0.0586 | 79% |
| 98K | 98,229 | $0.3364 | 27,410 | $0.0611 | 82% |
| 158K | 158,225 | $0.6025 | 26,910 | $0.0734 | 88% |
| 159K | 158,745 | $0.5476 | 26,959 | $0.0191 | 97% |

Not uniformly dramatic — the two smallest sessions (under ~30K) save less
because `/oct-wake`'s own fixed overhead (shared cache + the checkpoint
itself) is a bigger fraction of a tiny session. But 6 of these 8 sessions
land at 62K+, which is a normal size for a real working session — and
that's exactly where savings are consistent, 76–97%.

If the status bar is on (`/oct-pulse`), you don't even need to run the
command yourself — the context size is already sitting there live, before
and after.

### Reproduce the table yourself

`scripts/oct-benchmark.sh` is the actual script that generated the table
above — it's in the repo, not a one-off. It makes real `claude --resume`
and `claude -p` calls against your own session history (same model pinned
on both sides so a version mismatch doesn't blow the shared cache and skew
the result), so running it spends a small amount of real API usage.

```bash
# one session vs. one checkpoint
scripts/oct-benchmark.sh <session-id> ~/.claude/summaries/<checkpoint>.md

# auto-pick your largest recent session + latest checkpoint
scripts/oct-benchmark.sh --auto

# sweep N real sessions spread across your own history's size range,
# one fixed checkpoint throughout — prints a summary table like the one above
scripts/oct-benchmark.sh --sweep 8
```

Pin the model with `OCT_BENCH_MODEL` (default `sonnet`) if you want a
different one on both sides.

## What's in it

- **`/oct-nap`** — write a ~1-2k token checkpoint before `/clear`
- **`/oct-wake`** — load the latest checkpoint (not the whole old session) in
  one shot; `/oct-wake <keyword>` also searches curated long-term memory
- **`/oct-dream`** / **`/oct-sleep`** — periodic memory consolidation
- **`/oct-pulse`** — per-response token/cost breakdown (Stop hook), plus a
  persistent status-bar line with Anthropic's *official* 5h/7d rate-limit %
  and a reset-vs-ETA comparison so you can tell at a glance whether you'll
  hit the cap before the window resets on its own
- **`/oct-checkup`** — per-call token/cost table for a session;
  `/oct-checkup habits` scans the last N days of transcripts for spending
  patterns (long answer → immediate short question, chatter on a fat
  context, repeated corrections, fat session ended without a checkpoint)
  and proposes one-line memory rules — you pick which to save
- **Read-dedup hook** — blocks a byte-identical re-read of a file already
  read this session (same path, mtime, size, offset/limit), so duplicate
  content doesn't double up in context

## Install

```bash
git clone <this-repo> ~/.claude/skills/oct-toolkit
```

(Not `~/.claude/plugins/` — a bare clone there is never auto-discovered.
`~/.claude/skills/<name>/.claude-plugin/plugin.json` is what Claude Code
picks up on its own, no marketplace or install step needed.)

Then open Claude Code. You'll see one line:

```
🐙 oct-toolkit installed. The status bar isn't on yet — run /oct-pulse to enable it.
```

Type `/oct-pulse`, answer yes, done. That's the whole setup.

<details>
<summary>Why that one step is manual, and what it writes</summary>

Commands and hooks (`SessionStart`, `PreToolUse[Read]`, `Stop`) load
automatically with the plugin. The bottom status bar is different: it's a
single `statusLine` setting in `~/.claude/settings.json`, and a plugin
shouldn't silently take it over — you might already be using it for
something else. So `/oct-pulse` asks first, then writes:

```json
"statusLine": {
  "type": "command",
  "command": "python3 ~/.claude/skills/oct-toolkit/scripts/usage-analyze.py --statusline-hook"
}
```

Without it, the per-response cost line still works; the 5h/7d quota
numbers (which come from Anthropic's official `rate_limits`, delivered
only through the statusLine payload) won't appear.

If your Claude Code prefers marketplace installs, add this repo as a
marketplace source and install `oct-toolkit` from it — same result.
</details>

## Requirements

- Claude Code ≥2.1.80 for official `rate_limits` (older versions fall back
  automatically)
- Python 3

## License

MIT
