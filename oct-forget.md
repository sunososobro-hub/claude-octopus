# oct-forget

Remove or disable Claude Octopus tools.

## Usage

```bash
/oct-forget              # Show what to remove
/oct-forget all          # Remove everything
/oct-forget oct-focus    # Remove specific tool
/oct-forget --help       # Show help
/oct-forget help         # Show help
```

When run without arguments, shows:
```
🚮 Uninstall Claude Octopus

Currently installed:
  ✓ oct-wake      (cost optimization onboarding)
  ✓ oct-focus     (model suggestions)
  ✓ oct-dream     (memory consolidation)
  ✓ oct-save      (save sessions)
  ✓ oct-recall    (restore sessions)

What to remove?
  [oct-wake]      [oct-focus]     [oct-dream]
  [oct-save]      [oct-recall]
  [all]           [cancel]
```

## What It Does

- Removes selected skills from `~/.claude/commands/`
- Removes config from `~/.claude/settings.json`
- Keeps summaries (you can delete manually if needed)
- Can be re-installed anytime

## Examples

```bash
/oct-forget oct-focus    # Remove just model suggestions
/oct-forget all          # Remove everything
```
