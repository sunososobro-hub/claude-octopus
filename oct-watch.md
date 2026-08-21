# oct-watch

Show per-response token usage after every Claude response (Stop hook).

## Usage

```bash
/oct-watch           # Show current status (enabled/disabled)
/oct-watch enable    # Add Stop hook → show usage after each response
/oct-watch disable   # Remove Stop hook
```

## Output (when enabled)

After each response, the harness prints:
```
⌚ sonnet-4-6  In:2($0.00)  CR:57.9K($0.02)  CW:837($0.00)  Out:123($0.00)  =$0.0224
```

## How It Works

### Status check (no args)

Read `~/.claude/settings.json`. Check if `hooks.Stop` contains an entry with `--watch`.

If enabled:
```
⌚ oct-watch  enabled
   Stop hook: active — usage shown after each response
   Disable: /oct-watch disable
```

If disabled:
```
⌚ oct-watch  disabled
   Enable: /oct-watch enable
```

### Enable

Read `~/.claude/settings.json`. Add to `hooks.Stop`:

```json
{
  "type": "command",
  "command": "python3 -c \"import sys,json,subprocess,time; time.sleep(1); r=subprocess.run(['python3','/home/alonso/.claude/scripts/usage-analyze.py','--watch'],capture_output=True,text=True); print(json.dumps({'systemMessage':r.stdout.strip()}))\""
}
```

Write back and confirm:
```
✅ oct-watch enabled — usage will appear after each response.
```

### Disable

Read `~/.claude/settings.json`. Remove any entry in `hooks.Stop` that contains `--watch`. Write back and confirm:
```
✅ oct-watch disabled.
```
