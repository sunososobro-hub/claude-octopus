# Security policy

## Reporting a vulnerability or a leaked secret

Please do not open a public issue for a vulnerability or for a real credential.
Use GitHub private vulnerability reporting (Security tab, "Report a vulnerability") for this repository.

If the report contains a real key, token or password, revoke it and issue a new one first.
Treat anything that was posted publicly as already leaked.

## What this repository does to prevent leaks

- CI runs the unit tests, `scripts/leak_check.py`, and a gitleaks scan of the full history
  on every push, pull request and weekly.
- `.gitleaks.toml` extends the default gitleaks rules with extra credential patterns.
- Maintainers also run the same checks in a local pre-commit hook.

## Scope

This is a client-side plugin made of scripts and prompts. It makes no network calls of its own
beyond what Claude Code does. Reports about the scripts running unintended commands, reading
files outside the Claude configuration directory, or writing sensitive data to disk are in scope.
