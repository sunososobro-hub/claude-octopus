---
description: "Nap: before leaving or /clear, write where you got to, what you found, and what's next as a ~1-2k token checkpoint in ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/"
---

# oct-nap

Save current session state as a ~1-2k token checkpoint.

## When to run

Manually via `/oct-nap`, or when a UserPromptSubmit line from oct-toolkit asks for it (30+ turns or context growth past the cold start). Never interrupt the user's request for it; the nap runs in the background.

## Background mode (default)

1. Spawn one Agent call: `subagent_type: "fork"`, `run_in_background: true`, `description: "oct-nap checkpoint"`, prompt: "Run steps 1-6 of oct-nap.md (checkpoint, same-project merge, index, archive, savings line). Reply with only the output lines." Do not wait for it: answer the user's actual request or, for a bare `/oct-nap`, say `napping in background` and stop.
2. When the fork's completion notice arrives, print its output lines as-is, once.
3. If the Agent tool, the fork type or background runs are unavailable or error out, run steps 1-6 yourself in the foreground.
4. Memory tidy (skip if the fork failed): run `$PY "$SCRIPT" --tidy-check` with `SCRIPT` and `PY` set as in step 6. If it prints `tidy: N lines in <dir>`, spawn a separate plain agent (`subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true`, `description: "tidy memory"`) with this prompt: "Read only <dir>/MEMORY.md and the memory files it links. Merge duplicates and near-duplicates into one file each, keeping every distinct fact and fixing MEMORY.md lines (`- [Title](file.md) - hook`). Move stale or finished notes to <dir>/archive/ and drop their index lines. Reply with one line of counts." Print exactly `tidying memory in background`. No output means nothing to do.

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
- [ ] [next action after that]

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

- `## Awaiting Reply`: optional; omit if nothing is pending.
- `## Due`: include only if the user stated a deadline/urgency this session; use their words (date as YYYY-MM-DD if given). Never infer one. Otherwise omit the section.
- `## Running agents` / `## Pending dispatch`: omit if empty. `## User quotes index` is appended by step 3b; never write it by hand.
- `## Decisions / Watch`: chosen numbers/values, explicitly rejected approaches (with reason), unverified assumptions, unanswered questions. Omit if none. Never put credentials, keys, tokens or passwords here; point to where they live.

## Instructions

1. Generate the summary in the format above. Write `## Next Steps` as separate `- [ ]` items.
   If re-saving over the same task (you hold an open checkpoint's hash from this session, e.g. via `/oct-wake`), carry forward every `- [ ]` Next Steps item and every `## Decisions / Watch` line from that checkpoint as `[ ]` (open), `[x]` (done) or `[-] dropped: <reason>`; keep `- [x]` items as done. Mandatory.
2. Same-project merge: from `index.md`, take the other active lines (not this checkpoint's own hash) with this checkpoint's project tag (skip the tag if it is vague or empty). Read only those files. Add every open `- [ ]` item and `## Decisions / Watch` line not already present to the new Next Steps / Decisions / Watch, deduped. Items from other checkpoints marked `[x]` or `[-] dropped` are not carried.
3. Save to `${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/{8-char-hash}.md` with the Write tool.
3b. Quotes index: replace any existing `## User quotes index` block in the file, then append the extract (`--session` pins this transcript). Add every user ask or approved proposal with no matching Next Steps item as a `- [ ]` item, in the user's words:

   ```bash
   S="${CLAUDE_PLUGIN_ROOT}/scripts"
   PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
   $PY "$S/nap_extract.py" --session ${CLAUDE_SESSION_ID} >> ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/{hash}.md
   ```

3c. In-flight work: write each background agent or worktree still running, and each dispatch the user asked for that did not go out, into `## Running agents` / `## Pending dispatch`. Every running line needs `Done when:` conditions joined by `&&`, from: `pushed <repo> <branch>`, `on-master <repo> <ref>`, `in-tree <repo> <path-glob>` (a matching file is on the default branch's tree), `file <path>`, `agent <agentId>`. Add `- [ ] Collect <name>` to Next Steps per running agent. Then, with the `S=` and `PY=` lines above repeated in the same Bash call, run `$PY "$S/nap_verify.py" ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/{hash}.md` and fix any `no completion condition` line.
4. Append/update its line in `${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/index.md` (create with a header if missing), one line per checkpoint:

   ```
   {hash} | {date} {time} | {project-tag} | {task one-liner}
   ```

   `{project-tag}` comes from this checkpoint's `## Task` line only: ticket ID, repo/app name, or initiative name (the same identifier `/oct-wake` clusters by). When re-saving an existing hash, replace its line in place; no duplicates.
5. Archive: `mkdir -p ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/archive`, move every same-project checkpoint read in step 2 (now carried forward, or with all next steps done) there and delete its line from `index.md`. Other projects' checkpoints are never touched. Fold any durable gotcha from an archived checkpoint into the new `## Decisions / Watch`.
6. Output only (always print the second line; do not print the summary content):

```
✅ ${CLAUDE_CONFIG_DIR:-~/.claude}/summaries/{hash}.md
Resume: /oct-wake {hash}
```

If checkpoints were archived, add a third line `Archived N older {project-tag} checkpoint(s)`.

Then print the savings line (nothing is printed if it cannot be computed):

```bash
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/usage-analyze.py"
PY=$(for p in python3 python "py -3"; do $p -c 1 >/dev/null 2>&1 && { echo "$p"; break; }; done)
$PY "$SCRIPT" --nap-savings={hash} 2>&1
```

Show its output as-is (a second `estimate:` line gives the net saving after the cold-start cost of the fresh session, from the user's own rolling baseline; it may say it does not pay off or that history is too thin, show that too); for a manual run also tell the user once they can `/clear` and the checkpoint auto-resumes.
