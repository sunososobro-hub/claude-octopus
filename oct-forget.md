# oct-forget

Remove or disable Claude Octopus tools.

Choose to forget what you learned.

## Usage

```bash
/oct-forget
```

Shows:
```
🚮 Uninstall Claude Octopus

Currently installed:
  ✓ oct-wake      (onboarding & setup)
  ✓ oct-focus     (model suggestions)
  ✓ oct-dream     (memory consolidation)
  ✓ oct-rest      (save sessions)
  ✓ oct-recall    (restore sessions)

What to remove?
  [oct-wake] [oct-focus] [oct-dream]
  [oct-rest] [oct-recall]
  [all] [cancel]
```

## What It Does

- Removes selected skills from `~/.claude/commands/`
- Removes config from `~/.claude/settings.json`
- Keeps summaries (can delete manually if needed)
- Can be re-installed anytime

## Examples

```bash
/oct-forget oct-focus    # Remove just model suggestions
/oct-forget all          # Remove everything
```

## Re-installation

Anytime you want to use Claude Octopus again:
```bash
/oct-wake
```
