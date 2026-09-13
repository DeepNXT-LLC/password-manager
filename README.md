# Password Manager — encrypted local vault (Stage 1)

A Windows desktop password manager built with Python and Tkinter.

This private review branch changes the original prototype into a first-stage,
single-owner vault. Password records are stored in an encrypted local `.vault`
file protected by a master password. The master password is never saved by the
application.

## What this stage supports

- Password Book, Mobile Devices, Computers, and Admin tabs
- Add, update, delete, search, and 90-day update reminders
- Passwords masked in the table and form until the owner chooses **Show**
- Password generation using Python's cryptographically secure `secrets` module
- Encrypted per-category and full-vault backups using AES-256-GCM and scrypt
- CSV/XLSX header-only templates for preparing imports
- CSV/XLSX imports as a deliberate one-time migration path

## What this stage does not claim

- This is not yet a multi-user team service.
- There are no team accounts, roles, sharing rules, audit logs, or recovery
  workflow yet.
- PostgreSQL is intentionally not used in this stage because the original
  PostgreSQL schema stores passwords as plaintext.
- The application cannot protect secrets from someone who controls the Windows
  account, machine, or process running it.

Do not call this production-ready for team use until Stage 2 has separately
specified and verified identities, authorization, recovery, auditability,
concurrency, deployment, and operational backup/restore.

## Security rules

- The master password must be at least 12 characters. If it is forgotten, the
  application cannot recover the vault.
- The encrypted vault is `json_files/password_data.vault`.
- A legacy `json_files/password_data.json` is rejected. It is not silently read
  or converted because it may contain plaintext credentials.
- Password backups must use `.vault`. Plaintext JSON/CSV/XLSX password exports
  are disabled.
- Empty CSV/XLSX templates are allowed because they contain no credentials.
- Keep vault backups private and test that they can be unlocked before relying
  on them.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running

```powershell
python password_manager.py
```

The first run asks the owner to create a master password. Later runs ask to
unlock the existing vault.

## Testing

Run from this repository. The `--confcutdir=.` option prevents an unrelated
parent-folder pytest configuration from being loaded.

```powershell
python -m pytest -q --override-ini addopts= --confcutdir=.
```

## Repository structure

```text
password_manager.py                 # Tkinter UI and encrypted-vault CRUD
password_generator.py               # secure password generation
vault_crypto.py                     # scrypt + AES-GCM vault envelope
tests/                              # focused security and behavior tests
sql_functions/                      # retained source reference; not used in Stage 1
word_list.json                      # public word list for generation
requirements.txt
```

## License

This project is licensed under the MIT License. See `LICENSE.txt`.
