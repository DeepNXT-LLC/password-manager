# Password Manager (Tkinter + PostgreSQL/JSON)

A desktop password manager built with Python and Tkinter.

This application helps track account credentials across multiple categories, 
generate secure passwords from a word list, and import/export backup data in 
JSON, CSV, and XLSX formats.

## Features

- Multi-tab credential management:
	- Password Book
	- Mobile Devices
	- Computers
	- Admin
- Full CRUD operations (Add, Update, Delete, Search)
- Password generator (word-based + symbol + digits)
- Optional clipboard copy support via `pyperclip`
- Import and export support:
	- Per-category backups
	- Full multi-category backups
	- Header-only template exports for CSV/XLSX imports
- Password update reminder workflow:
	- Tracks `updated_at`
	- Flags records older than 90 days
	- Displays due items in a dedicated Reminders tab
- Storage backend auto-selection:
	- Uses PostgreSQL when available
	- Falls back to local JSON storage when DB connection is unavailable

## Tech Stack

- Python 3
- Tkinter (GUI)
- PostgreSQL (`psycopg2`) for primary storage
- JSON file fallback storage
- `openpyxl` for `.xlsx` import/export
- `python-dotenv` for environment variable loading

## Repository Structure

```text
password_manager/
├── password_manager.py              # Main GUI application
├── password_generator.py            # Password generation utilities
├── postgresql.py                    # PostgreSQL connection helper
├── password_data.json               # JSON fallback data store
├── public_config.json               # Public word list config
├── word_list.json                   # Public word list
├── requirements.txt
├── LICENSE.txt
├── README.md
├── json_files/
│   └── word_list.json               # Private/local word list option
└── sql_functions/
		└── password_manager_table.sql   # Example base table DDL
```

## Installation

1. Create and activate a virtual environment.

```bash
python -m venv .venv
```

Windows (PowerShell):

```bash
.venv\Scripts\Activate.ps1
```

Windows (cmd):

```bash
.venv\Scripts\activate.bat
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

## Configuration

### 1) Environment variables (.env)

Create a `.env` file in the project root for PostgreSQL access:

```env
POSTGRESQL_HOST=host
POSTGRESQL_PORT=port
DATABASE=password_manager
POSTGRESQL_USER=username
POSTGRESQL_PASSWORD=your_password
```

If these values are missing or the database is unreachable, the app automatically 
uses `password_data.json` for storage.

### 2) Word list source

Password generation uses a JSON array of words and resolves sources in this order:

1. `json_files/private_config.json` -> `word_list_path` (if present)
2. `public_config.json` -> `word_list_path`
3. `json_files/word_list.json`
4. `word_list.json`

Example `public_config.json`:

```json
{
	"word_list_path": "word_list.json"
}
```

Expected word list format:

```json
["apple", "sunset", "rocket", "bridge"]
```

At least 2 valid words are required.

## Database Setup (Optional but Recommended)

You can let the app create required tables automatically on startup, 
or manually run the SQL in `sql_functions/password_manager_table.sql` as a baseline.

On startup, the app ensures category tables exist for:

- `password_manager`
- `password_manager_mobile_devices`
- `password_manager_computers`
- `password_manager_admin`

Each table enforces uniqueness on:

- `employee_name`
- `account_name`
- `username`

## Running the App

```bash
python password_manager.py
```

The UI opens with category tabs and a Reminders tab.

## Import/Export Formats

### Supported file types

- `.json`
- `.csv`
- `.xlsx`

### Canonical fields

- `employee_name` / `Employee Name`
- `account_name` / `Account Name`
- `username` / `Username`
- `account_password` / `Password` / `Account Password`
- `notes` / `Notes`
- `category` / `Category` (required for full multi-category tabular imports)

### Import behavior

- Required fields: employee name, account name, username, password
- Duplicate detection key: employee + account + username
- Existing matches are updated (upsert behavior)
- Invalid rows are skipped and reported

## Password Reminder Logic

- A record is considered due when `updated_at` is older than 90 days.
- Due records are grouped and shown in the Reminders tab.
- A startup warning summarizes due counts by category.

## Security Notes

- Passwords are stored as plain text in this project (database and JSON fallback).
- Use this project only in trusted/internal environments unless you add encryption 
  and stronger access controls.
- Do not commit real credentials or private `.env` values.

## Troubleshooting

- `psycopg2` install issues on Windows:
	- Ensure Python and pip are up to date.
	- If build errors occur, install PostgreSQL client tools and Visual C++ Build Tools, 
      or use a compatible wheel.
- `.xlsx` import/export errors:
	- Verify `openpyxl` is installed.
- Password generator errors:
	- Confirm the configured word list file exists and is a JSON array of strings.

## License

This project is licensed under the MIT License. See `LICENSE.txt`.
