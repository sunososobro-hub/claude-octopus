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

1. Spawn one Agent: `subagent_type: "fork"`, `run_in_background: true`, `description: "oct-nap checkpoint"`, prompt: "Run steps 1-6 of oct-nap.md (checkpoint, same-project merge, index, archive, savings line). Reply with only the output lines." Do not wait: answer the user's request, or for a bare `/oct-nap` say `napping in background` and stop.
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

1. Generate the summary in the format above; `## Next Steps` as separate `- [ ]` items. If re-saving the same task (you hold an open checkpoint's hash from this session, e.g. via `/oct-wake`), carry forward every `- [ ]` Next Steps item and every `## Decisions / Watch` line from it as `[ ]`, `[x]` or `[-] dropped: <reason>`; keep `- [x]` as done. Mandatory.
2. Same-project merge: from `index.md` take the other active lines (not this hash) with this checkpoint's project tag (skip if vague or empty). Read only those files. Add every open `- [ ]` item and `## Decisions / Watch` line not already present to the new Next Steps / Decisions / Watch, deduped. Items marked `[x]` or `[-] dropped` are not carried.
3. Save to `$SUM/{8-char-hash}.md` with the Write tool.
3b. Quotes index: replace any existing `## User quotes index` block in the file, then append the extract (`--session` pins this transcript). Add every user ask or approved proposal with no matching Next Steps item as a `- [ ]` item, in the user's words:

   ```bash
   $PY "$S/nap_extract.py" --session ${CLAUDE_SESSION_ID} >> $SUM/{hash}.md
   ```

3c. In-flight work: write each still-running background agent or worktree, and each requested dispatch that did not go out, into `## Running agents` / `## Pending dispatch`. Every running line needs `Done when:` conditions joined by `&&`, from: `pushed <repo> <branch>`, `on-master <repo> <ref>`, `in-tree <repo> <path-glob>` (a matching file is on the default branch's tree), `file <path>`, `agent <agentId>`. Add `- [ ] Collect <name>` to Next Steps per running agent. Then, with Setup in the same Bash call, run `$PY "$S/nap_verify.py" $SUM/{hash}.md` and fix any `no completion condition` line.
4. Append/update its line in `$SUM/index.md` (create with header if missing), one per checkpoint: `{hash} | {date} {time} | {project-tag} | {task one-liner}`. `{project-tag}` comes from this `## Task` line only: ticket ID, repo/app, or initiative name (what `/oct-wake` clusters by). When re-saving a hash, replace its line in place.
5. Archive: `mkdir -p $SUM/archive`; move every same-project checkpoint read in step 2 (now carried forward, or all next steps done) there and delete its `index.md` line. Never touch other projects'. Fold any durable gotcha from an archived checkpoint into the new `## Decisions / Watch`.
6. Output only (always print line 2; never the summary content), with `$SUM` resolved:

```
✅ $SUM/{hash}.md
Resume: /oct-wake {hash}
```

If checkpoints were archived, add `Archived N older {project-tag} checkpoint(s)`.

Then the savings line (nothing printed if it cannot be computed): `$PY "$SCRIPT" --nap-savings={hash} 2>&1`. Show its output as-is (a second `estimate:` line gives the net saving after the fresh session's cold-start cost, from the user's rolling baseline; it may say it does not pay off or history is too thin: show that too). For a manual run also tell the user once they can `/clear` and the checkpoint auto-resumes.
