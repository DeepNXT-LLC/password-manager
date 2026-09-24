# Single-user hardening review — proposal for Brandon

This branch starts from `theOrganizedMind/password-manager` at
`276e5c0a668a77234b95e22ce0ea87884fbc04a0`, copied exactly into an
isolated review base before these edits. It is a Windows, one-owner desktop
vault review. It is **not** the separate Azure/multi-user project, a release, or
proof that the app is production-ready.

## Evidence-backed changes

| Finding on the exact base | Proposed change | Reproduction/check |
| --- | --- | --- |
| An export path could be the live vault, or an alias that points to it. A directory alias switched after a path check could still redirect a save into the vault. | Reject obvious aliases and commit backup files with an atomic create-if-absent operation. Existing backup names are refused. | `tests/test_storage.py` checks direct, relative, symlink and hardlink aliases, existing backups, and a directory-alias switch for both export paths. |
| An exception string or traceback could contain a credential and reach a plaintext log. | Record only a fixed operation identifier in plaintext logs, without exception content. Unexpected add/update failures get a generic UI error; selected validation `ValueError` messages still appear in the UI. | `tests/test_adversarial_repairs.py` and `tests/test_ui_security.py` inject synthetic secret markers into the unexpected-failure paths and assert they do not appear in logs or prompts. These tests do not establish that every possible validation message is secret-free. |
| Passwords with meaningful leading/trailing spaces were modified by form/import cleanup. | Preserve the password field byte-for-byte as text; still reject empty or whitespace-only values. | `tests/test_adversarial_repairs.py` checks forms, imports, and whitespace-only refusal. |
| A one-character generator setting could yield a trivially guessable password. A custom word list could appear to have many choices while producing ambiguous, colliding outputs. | Use `secrets`, validate bounded settings and a conservative estimated randomness floor, and require distinct prefix-free rendered word tokens. | `tests/test_password_generator.py` checks weak settings, token collisions, and output formats. Randomness estimates depend on the quality of the configured word list. |
| Two app instances could read the same vault and silently lose one writer's change. A stale selection could edit/delete even after the record changed away and back within one timestamp second. | Lock full local transactions and require a selection-time snapshot with a monotonic per-record revision; migrate earlier encrypted vault records on unlock. | `tests/test_storage_concurrency.py` and `tests/test_vault_concurrency.py` cover competing writers, stale edits/deletes, the A→B→A sequence, and old-vault revision migration. |
| A vanished vault was rejected by an already-running instance but silently re-created as empty on restart. A manual “create empty vault, then import backup” recovery could overwrite newer data after an interruption. | Persist a non-secret initialization marker outside the vault directory. When the vault is missing, validate and restore a complete encrypted backup directly, without an intermediate empty vault. Reject unknown top-level backup fields rather than silently drop data from a future format. | `tests/test_storage_concurrency.py` checks same-instance loss, full-directory loss after restart, partial/unknown-format refusal, existing-vault refusal, and synthetic full-backup recovery. The marker is not tamper-proof; deleting both vault and marker defeats this accidental-loss signal. A visible missing-vault recovery and true power-loss durability remain unproven. |
| A contradictory encrypted backup with both flat `records` and category-keyed data could be accepted through category import. | Reject mixed shapes before either import path writes. Keep legitimate partial-category backups supported. | `tests/test_adversarial_repairs.py` checks rejection without vault change and accepted partial backups. |
| A backup encrypted under another profile's master password could not be imported into an open destination vault. Matching account identities could silently upsert and replace destination passwords. | Accept an optional backup password for category and full imports. Label only selected-backup decryption failures as backup unlock failures. Under the local vault lock, reject any normalized case-insensitive account identity already in the destination or repeated in the batch before one write. | Focused synthetic storage and UI checks passed. A headed Windows walkthrough of full-backup import into a nonempty disposable profile is reported and partially corroborated by screenshots; no real vault data was used. A separately documented headed category-import sequence is not included in the follow-up evidence. |

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

### Disposable Windows test record

An independent reviewer tested an archive of the source commit
`33205f02614843f30127dcd5c7d0ec41900655cb` in a disposable Windows
directory with Python 3.13.7 and the pinned `requirements.txt` versions
(including pytest 9.1.1). Python bytecode writes and third-party pytest plugin
autoload were disabled. The reviewer ran the six storage/UI/adversarial/generator
modules with `-q -rs --override-ini addopts= --confcutdir=. -p no:cacheprovider`:

```text
129 passed in 31.89s
exit code: 0
```

The same options applied to `tests/test_vault_crypto.py` produced:

```text
4 passed in 0.85s
exit code: 0
```

These are two test commands, not a single `133 passed` pytest transcript.
Neither summary reported skips. The runs used synthetic data and do not prove
headed UI behavior or true power-loss durability.

A separate verbose run on the same disposable source archive selected the five
symlink/alias cases with `-k 'symlink or guard_alias_swap'`. Its recorded output
was:

```text
tests/test_storage.py::test_export_rejects_live_vault_destination_without_changing_it[symlink-False] PASSED
tests/test_storage.py::test_export_rejects_live_vault_destination_without_changing_it[symlink-True] PASSED
tests/test_storage.py::test_export_does_not_overwrite_vault_after_guard_alias_swap[False] PASSED
tests/test_storage.py::test_export_does_not_overwrite_vault_after_guard_alias_swap[True] PASSED
tests/test_vault_concurrency.py::test_sidecar_symlink_fails_closed_when_supported PASSED
5 passed, 6 deselected in 1.34s
exit code: 0
```

The six deselections were other parameter cases under the three selected test
functions, not skips. This proves execution in the tested Windows environment,
not protection against arbitrary filesystem control.

### Current review-branch verification

The earlier app-code commit is `da23351f55e6ac26a28a03860e65671db977386a`.
The subsequent `555ded63afd219c0c0ade7525415841e372abadf` commit adds tests
without changing app source. The later app-code commit
`2f8f72e8c44c95fba21d22edd1ca5b9a90c2e62d` corrects two recovery
messages in `password_manager.py` and asserts their wording in
`tests/test_ui_security.py`; it does not change vault storage behavior.
On that code, the full command
`python -m pytest -q -ra -p no:cacheprovider` returned `152 passed in 52.95s`
(exit code 0, no skips or failures) using an isolated Python 3.13.7 environment
with Tk 8.6.15. The two focused recovery UI cases returned `2 passed in 1.29s`;
the scripted real-Tk backup smoke module returned `2 passed in 9.73s`.

The suite includes synthetic tests that construct real Tk windows and widgets.
They exercise startup retry/cancel, the Clear button, encrypted backup export
and refusal to replace an existing file, wrong-backup-password cancellation
without changing the destination vault, import between disposable profiles,
masked password display, and reopening the destination with both records
intact.

These tests invoke the app's buttons, but replace native file, password, and
message dialogs with test doubles. They are scripted real-window checks, not
human clicks through native dialogs, and do not cover Tk 8.6.12. All vault and
backup data in these tests are synthetic and disposable. Nick separately
reports a person-clicked Windows 11 Home 25H2, Python 3.13.14, Tk 8.6.15
walkthrough on `555ded6`. That build predates the two recovery wording changes
described here, so his report does not verify the exact current strings.

Bill manually launched a byte-identical disposable copy of the patched app.
The remnant warning displayed the isolated vault folder, preservation
instruction, and no-deletion statement. He then tested the missing-vault
prompt, chose No, and the app exited without creating a vault while the
quarantined fake vault and remnant remained. The test setup restored the fake
vault afterward. This walkthrough supports those
specific UI outcomes; no Tk version is attributed to this manual run. The
automated tests assert the prompt wording, folder path, preservation guidance,
scan scope, and retained files. A separately documented human category-import
sequence and a current-code Tk 8.6.12 check are not in this evidence. Brandon's
supported Windows/Tk versions, headed-evidence acceptance, and decision on
excluding the inactive PostgreSQL path remain open. The PR remains a draft for
Brandon's review.

Residual limits to discuss explicitly: plaintext CSV/XLSX originals remain
after import; clipboard history and process memory can hold secrets; the app
has no idle lock or verified crash/power-loss recovery; the local lock covers
only cooperating same-host app instances; and the manual remnant walkthrough
does not establish physical crash or power-loss durability. A user or other
program with control of the Windows account can bypass these safeguards.

PostgreSQL import remains unsupported and inactive. Export dialogs suggest
timestamped names and existing files are not replaced. Startup warns if
temporary encrypted files remain beside the vault after an interruption; the
app leaves those files in place for manual review. Deep reports headed Windows
coverage of the import password retry and cancellation; his September 24
follow-up includes a time-ordered record and screenshots of the visible prompts
and outcomes. Those images do not independently establish every click, the
reported close/reopen step, or the reported vault hashes, because the vault
files were not included. Nick's later person-clicked report covers a retained
temporary file and its warning, but does not establish physical power-loss
recovery. Deep attests that he personally clicked through startup,
selection, and Clear on Tk 8.6.12 without a hang on an earlier staged candidate;
that report does not verify the current app source. Bill's
partial walkthrough reached a successful full-backup import into a nonempty
disposable profile, but he stopped before a close/reopen persistence check.
Earlier independent settled-code Windows test commands passed 133 cases in
total with none skipped, including the five symlink/alias cases. Two of Nick's smaller UX
notes remain: startup does not scan user-selected backup export folders for
temporary files, and the backup Save picker has no app-provided default folder.
The picker may initially open in Documents according to Nick's earlier report.
These folder behaviors remain product choices. Neither the tester reports nor
the synthetic tests establish production readiness.

Questions for Brandon: Are these changes aligned with the intended single-user
app? Does he want the stricter backup no-overwrite behavior and the local
revision migration in his mainline? Are there existing user vaults or backup
formats we have not seen that need a separate migration test? A PR should be
reviewed on its merits; this document is not a request to merge sight unseen.
