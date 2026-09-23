# Single-user hardening review — proposal for Brandon

This branch starts from `theOrganizedMind/password-manager` at
`276e5c0a668a77234b95e22ce0ea87884fbc04a0`, copied exactly into the
private review base before these edits. It is a Windows, one-owner desktop
vault review. It is **not** the separate Azure/multi-user project, a release, or
proof that the app is production-ready.

## Evidence-backed changes

| Finding on the exact base | Proposed change | Reproduction/check |
| --- | --- | --- |
| An export path could be the live vault, or an alias that points to it. A directory alias switched after a path check could still redirect a save into the vault. | Reject obvious aliases and commit backup files with an atomic create-if-absent operation. Existing backup names are refused. | `tests/test_storage.py` checks direct, relative, symlink and hardlink aliases, existing backups, and a directory-alias switch for both export paths. |
| An exception string or traceback could contain a credential and reach a plaintext log. | Record only a fixed operation identifier and show a generic UI error, without logging exception content. | `tests/test_adversarial_repairs.py` and `tests/test_ui_security.py` inject synthetic secret markers and assert they do not appear in logs or prompts. |
| Passwords with meaningful leading/trailing spaces were modified by form/import cleanup. | Preserve the password field byte-for-byte as text; still reject empty or whitespace-only values. | `tests/test_adversarial_repairs.py` checks forms, imports, and whitespace-only refusal. |
| A one-character generator setting could yield a trivially guessable password. A custom word list could appear to have many choices while producing ambiguous, colliding outputs. | Use `secrets`, validate bounded settings and a conservative estimated randomness floor, and require distinct prefix-free rendered word tokens. | `tests/test_password_generator.py` checks weak settings, token collisions, and output formats. Randomness estimates depend on the quality of the configured word list. |
| Two app instances could read the same vault and silently lose one writer's change. A stale selection could edit/delete even after the record changed away and back within one timestamp second. | Lock full local transactions and require a selection-time snapshot with a monotonic per-record revision; migrate earlier encrypted vault records on unlock. | `tests/test_storage_concurrency.py` and `tests/test_vault_concurrency.py` cover competing writers, stale edits/deletes, the A→B→A sequence, and old-vault revision migration. |
| A vanished vault was rejected by an already-running instance but silently re-created as empty on restart. A manual “create empty vault, then import backup” recovery could overwrite newer data after an interruption. | Persist a non-secret initialization marker outside the vault directory. When the vault is missing, validate and restore a complete encrypted backup directly, without an intermediate empty vault. Reject unknown top-level backup fields rather than silently drop data from a future format. | `tests/test_storage_concurrency.py` checks same-instance loss, full-directory loss after restart, partial/unknown-format refusal, existing-vault refusal, and synthetic full-backup recovery. The marker is not tamper-proof; deleting both vault and marker defeats this accidental-loss signal. The visible restore and power-loss cases remain unproven. |
| A contradictory encrypted backup with both flat `records` and category-keyed data could be accepted through category import. | Reject mixed shapes before either import path writes. Keep legitimate partial-category backups supported. | `tests/test_adversarial_repairs.py` checks rejection without vault change and accepted partial backups. |

## Why these changes matter

- [OWASP Cryptographic Storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) recommends authenticated encryption for stored sensitive data. The existing AES-GCM vault is retained; these edits focus on data-integrity and exposure gaps around it. This vault stores *recoverable credentials for other services*, not a server's own login verifier, so one-way password hashing would not provide the required retrieval behavior.
- [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) says authentication passwords and other primary secrets should not be recorded in logs. Omitting arbitrary exception text is a deliberate tradeoff: the log identifies the failed operation but is less diagnostic.
- [Python's `secrets` documentation](https://docs.python.org/3/library/secrets.html) recommends cryptographically strong randomness for generating passwords; the default `random` generator is not for this purpose. A secure random source does not rescue an undersized or ambiguous output space, hence the settings and word-list checks.
- [MITRE CWE-362](https://cwe.mitre.org/data/definitions/362.html) describes lost integrity when shared state is read and changed without exclusive access. [MITRE CWE-367](https://cwe.mitre.org/data/definitions/367.html) describes check/use races. The lock covers cooperative same-host vault writes; the no-overwrite backup commit closes the demonstrated alias-switch overwrite path. Neither is a defense against someone who controls the Windows account or filesystem.

## Verification boundary and reviewer checklist

Run the pinned dependencies in `requirements.txt` on Windows, then run
`python -m pytest -q --override-ini addopts= --confcutdir=.`. Review the diff
against the pinned base and repeat the synthetic attack cases. Before real use,
perform a headed desktop walkthrough with made-up credentials, a clean backup
and restore on a disposable profile, interruption/power-loss checks, and a
manual review of filesystem permissions and recovery instructions. A test pass
does not establish production readiness. No real passwords or existing vaults
were opened to prepare this review.

Residual limits to discuss explicitly: plaintext CSV/XLSX originals remain
after import; clipboard history and process memory can hold secrets; the app
has no idle lock or verified crash/power-loss recovery; the local lock covers
only cooperating same-host app instances; and the manual restore sequence has
not been walked through with a visible Windows UI. A user or other program
with control of the Windows account can bypass these application safeguards.

Questions for Brandon: Are these changes aligned with the intended single-user
app? Does he want the stricter backup no-overwrite behavior and the local
revision migration in his mainline? Are there existing user vaults or backup
formats we have not seen that need a separate migration test? A PR should be
reviewed on its merits; this document is not a request to merge sight unseen.
