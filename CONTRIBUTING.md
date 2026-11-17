# Contributing

Thanks for helping. Please keep contributions free of private information.

## Before you submit

1. Run the tests: `python -m unittest discover -s tests -v`
2. Check your text or patch for identifiers that should not be published:
   `python scripts/leak_check.py <file>` (standard library only).
3. Secret scanning (keys, tokens, passwords) is done by gitleaks; leak_check only looks for
   identifying information. Scan with [gitleaks](https://github.com/gitleaks/gitleaks) using the repo config:
   `gitleaks detect --config .gitleaks.toml`

Anything the checks flag is rejected as a whole. We do not edit or redact submissions;
remove the item yourself and resubmit.

## What not to include

- Credentials of any kind: API keys, tokens, passwords, connection strings, webhook URLs,
  private keys, service-account files.
- Contact details, local file paths that include a user name, IP addresses, account or
  project ids, session ids, share links to private documents.
- Names of people, companies, customers or unreleased projects.

## Placeholders that are always fine

`<YOUR_API_KEY>`, `user@example.com`, `C:\Users\<you>`, `/home/<you>`, `example.com`, `127.0.0.1`.

## Suggestions and ideas

Please use the issue form (Issues, New issue) rather than opening a pull request for
contributed notes. Issues can be removed by maintainers if something sensitive slips in;
pull requests cannot. Code fixes through pull requests are welcome.

If you accidentally published a real secret, revoke it first, then tell us (see SECURITY.md).

## Maintainers

The allowlist for the leak check lives in `scripts/leak_allowlist.txt`; every entry needs a reason.
If a rule blocks legitimate text often, fix the rule rather than adding exceptions.
