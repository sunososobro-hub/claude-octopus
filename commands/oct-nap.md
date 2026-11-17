---
description: "Nap: before leaving or /clear, save where you got to, findings and next steps as a ~1-2k token checkpoint in ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/"
---

# oct-nap

Save session state as a ~1-2k token checkpoint.

Setup (prefix every Bash call; `SUM` = checkpoint dir, also used in prose):

```bash
SUM="${CLAUDE_CONFIG_DIR:-~/.claude}/summaries"
S="${CLAUDE_PLUGIN_ROOT}/scripts"; SCRIPT="$S/usage-analyze.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
```

## When to run

Manually via `/oct-nap`, or when an oct-toolkit UserPromptSubmit line asks (30+ turns or context growth past the cold start). Never interrupt the user's request; the nap runs in the background.

## Background mode (default)

1. Spawn one Agent: `subagent_type: "fork"`, `run_in_background: true`, `description: "oct-nap checkpoint"`, prompt: "Run steps 1-6 of oct-nap.md (checkpoint, same-project merge, check, index, archive, optional memory promotion, savings line). Reply with only the output lines." Do not wait: answer the user's request, or for a bare `/oct-nap` say `napping in background` and stop.
2. On the fork's completion notice, print its output lines as-is, once.
3. If Agent, the fork type or background runs are unavailable or error, run steps 1-6 yourself in the foreground.
4. Memory tidy (skip if the fork failed): `$PY "$SCRIPT" --tidy-check`. If it prints `tidy: N lines in <dir>`, spawn a plain agent (`subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`, `description: "tidy memory"`), prompt: "Read only <dir>/MEMORY.md and the memory files it links. Merge duplicates and near-duplicates into one file each, keeping every distinct fact and fixing MEMORY.md lines (`- [Title](file.md) - hook`). Move stale or finished notes to <dir>/archive/ and drop their index lines. Reply with one line of counts." Print exactly `tidying memory in background`. No output = nothing to do.

## Format

```markdown
# a1b2c3d4 | 2026-08-21 16:45

## Task
[what the user was working on]

## Due
[optional]

## Key Findings
- [important discoveries or decisions]

## Decisions / Watch
[optional]
- [specific value / rejected approach + reason / unverified assumption / open question]

## Next Steps
- [ ] [concrete, checkable next action]

## Running agents
- [optional: name | Done when: pushed <repo> <branch> && file <path>]

## Pending dispatch
- [optional: a dispatch the user asked for that has not gone out, with enough of the prompt to re-dispatch]

## Awaiting Reply
- [optional: a question the user asked someone else or an external answer still pending, with who/where]

## Related Memory Files
- [relevant memory files]

## Important Context
- [anything that would be lost after /clear]
```

- `## Due`: only if the user stated a deadline/urgency this session; their words (date as YYYY-MM-DD if given); never infer.
- `## Running agents` / `## Pending dispatch` / `## Awaiting Reply`: omit if empty. `## User quotes index` is appended by step 3b; never write it by hand.
- `## Decisions / Watch`: chosen values, rejected approaches (with reason), unverified assumptions, unanswered questions; omit if none. Never put credentials, keys, tokens or passwords; point to where they live.

## Instructions

1. Hash: `$PY "$S/nap_index.py" --new-hash` prints an unused 8-hex hash. Always use it; never invent or reuse a hash (reused hashes collide with archived checkpoints). Generate the summary in the format above; `## Next Steps` as separate `- [ ]` items. If you hold an earlier checkpoint of this task (e.g. via `/oct-wake`), carry forward every `- [ ]` Next Steps item and every `## Decisions / Watch` line from it as `[ ]`, `[x]` or `[-] dropped: <reason>`; keep `- [x]` as done. Mandatory: step 3d checks it.
2. Same-project merge (hint/scope as in step 4): `$PY "$S/nap_index.py" --merge-candidates "{hint}" [--scope {scope}] --session ${CLAUDE_SESSION_ID} --exclude {hash}` prints `tag:` and the active checkpoints with exactly that tag (scope included) that no other open window owns, or `(none)`. Read only those files. Add every open `- [ ]` item and `## Decisions / Watch` line not already present, deduped. Items marked `[x]` or `[-] dropped` are not carried. Never read or merge any other checkpoint.
3. Save to `$SUM/{hash}.md` with the Write tool.
3b. Quotes index: replace any existing `## User quotes index` block in the file, then append the extract (`--session` pins this transcript). Add every user ask or approved proposal with no matching Next Steps item as a `- [ ]` item, in the user's words:

   ```bash
   $PY "$S/nap_extract.py" --session ${CLAUDE_SESSION_ID} >> $SUM/{hash}.md
   ```

3c. In-flight work: write each still-running background agent or worktree, and each requested dispatch that did not go out, into `## Running agents` / `## Pending dispatch`. Every running line needs `Done when:` conditions joined by `&&`, from: `pushed <repo> <branch>`, `on-master <repo> <ref>`, `in-tree <repo> <path-glob>` (a matching file is on the default branch's tree), `file <path>`, `agent <agentId>`. Add `- [ ] Collect <name>` to Next Steps per running agent. Then, with Setup in the same Bash call, run `$PY "$S/nap_verify.py" $SUM/{hash}.md` and fix any `no completion condition` line.
3d. Check (do not skip): `$PY "$S/nap_index.py" --check {hash} "{hint}" [--scope {scope}] --session ${CLAUDE_SESSION_ID}`.
   - `ERROR carry-forward ...` lists open items of this window's/session's earlier checkpoints (and the step-2 sources) that are missing here. Edit `{hash}.md` so each is carried as `- [ ]`, `- [x]` or `- [-] dropped: <reason>`, then re-run until it prints `check ok`. Never index while it errors (step 4 refuses anyway).
   - `WARN size ...`: over 9000 chars, so `/clear` auto-wake cannot inject it whole. Compact it (shrink Key Findings / Important Context / quotes index; keep Task, Next Steps, Decisions / Watch) and re-run once.
4. Index line (do not hand-edit `index.md`; the script re-runs the 3d check and writes under a lock):
   ```bash
   $PY "$S/nap_index.py" {hash} "{task one-liner, no |}" "{project-tag hint}" [--scope {scope}] --session ${CLAUDE_SESSION_ID}
   ```
   Hint = ticket ID, repo/app, or initiative from this `## Task` line (the identifier `/oct-wake` clusters by); the script maps it to the canonical tag in `summaries/tags.json`. Scope: when several windows work on one project in parallel (e.g. `mobile` vs `main`), pass a short `--scope` for this window's sub-stream so their checkpoints are never merged; omit it otherwise (an omitted scope is inherited from this window's/session's previous checkpoint). The window id comes from the environment. It prints `indexed: {hash} | {tag}` and, if any, `archived same-session: ...`, plus any `WARN` lines (orphan files: run `$PY "$S/nap_index.py" --repair`).
5. Archive: every checkpoint read in step 2 (carried forward, or all steps done): `$PY "$S/nap_index.py" --archive {hash...}` (moves to `summaries/archive/`, never overwrites, refuses checkpoints of other open windows). Never touch other projects. Fold any durable gotcha from an archived checkpoint into the new `## Decisions / Watch`.
5b. Optional, only when a Decisions / Watch line is a durable rule that outlives this task (a user preference, a standing constraint, a recurring gotcha), not task state: also save it to long-term memory. Memory dir and conventions are those in the system prompt's auto-memory section (`${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<slug>/memory/`): read its `MEMORY.md` first, update an existing note instead of adding a near-duplicate, otherwise write one note file (`feedback_*.md` / `project_*.md` with the front matter that dir already uses) and add one `- [Title](file.md) - hook` line to `MEMORY.md`. Keep the rule in Decisions / Watch too. Skip silently when nothing qualifies; never write secrets. Do not add scripts or hooks for this.
6. Output only (always print line 2; never the summary content), with `$SUM` resolved:

```
✅ $SUM/{hash}.md
Resume: /oct-wake {hash}
```

If checkpoints were archived (step 4 or 5), add `Archived N older {project-tag} checkpoint(s)`. Print any `WARN` line from 3d/4 as-is.

Then the savings line (nothing printed if it cannot be computed): `$PY "$SCRIPT" --nap-savings={hash} 2>&1`. Show its output as-is (a second `estimate:` line gives the net saving after the fresh session's cold-start cost, from the user's rolling baseline; it may say it does not pay off or history is too thin: show that too). For a manual run also tell the user once they can `/clear` now and the checkpoint auto-resumes; after more turns, nap again first (the checkpoint does not hold them).
