import csv
import json
import logging
import os
import re
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import password_generator
from postgresql import get_db_connection
from vault_crypto import VaultCryptoError, load_encrypted_file, save_encrypted_file

try:
    from openpyxl import Workbook, load_workbook
except ImportError:
    Workbook = None
    load_workbook = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log_files")
LOG_PATH = os.path.join(LOG_DIR, "password_manager.log")


def _configure_logging():
    """Configure application logging to a local rotating file."""
    logger = logging.getLogger("password_manager")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s event=%(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        fallback_handler = logging.StreamHandler()
        fallback_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fallback_handler)

    return logger


LOGGER = _configure_logging()


CATEGORY_LABELS = {
    "password_book": "Password Book",
    "mobile_devices": "Mobile Devices",
    "computers": "Computers",
    "admin": "Admin",
}

BASE_FIELDS = ["employee_name", "account_name", "username", "account_password", "notes"]
EXPORT_HEADERS = {
    "employee_name": "Employee Name",
    "account_name": "Account Name",
    "username": "Username",
    "account_password": "Password",
    "notes": "Notes",
    "category": "Category",
}


class PasswordManagerApp:
    """Main application controller for GUI interactions and user workflows."""

    def __init__(self, root, master_password):
        """Initialize the root window, storage backend, and user interface."""
        self.root = root
        self.root.title("Password Manager")
        self.root.geometry("1320x760")
        self.root.minsize(1180, 680)
        self.storage = StorageManager(master_password)
        self.tabs = {}
        self.reminder_tree = None
        self.settings_vars = {}
        self.settings_status_var = tk.StringVar(value="")

        self.build_ui()
        self.load_all_tabs()
        self.refresh_reminder_tab()
        self.check_password_reminders()

    def handle_ui_exception(self, title, user_message, action, exc):
        """Log detailed failure information and show a safe generic error."""
        backend = "encrypted_local_vault"
        LOGGER.exception(
            "ui_error action=%s backend=%s error_type=%s",
            action,
            backend,
            exc.__class__.__name__,
        )
        messagebox.showerror(title, user_message)

    def build_ui(self):
        """Build notebook tabs for accounts and reminders."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_password_book = ttk.Frame(self.notebook)
        self.tab_mobile_book = ttk.Frame(self.notebook)
        self.tab_computer_book = ttk.Frame(self.notebook)
        self.tab_admin = ttk.Frame(self.notebook)
        self.tab_reminders = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_password_book, text="📕Password Book")
        self.notebook.add(self.tab_mobile_book, text="📞Mobile Devices")
        self.notebook.add(self.tab_computer_book, text="💻Computers")
        self.notebook.add(self.tab_admin, text="🙍Admin")
        self.notebook.add(self.tab_reminders, text="🗓️Reminders")
        self.notebook.add(self.tab_settings, text="⚙️Settings")

        self.build_tab(self.tab_password_book, "password_book", "Password Book")
        self.build_tab(self.tab_mobile_book, "mobile_devices", "Mobile Devices")
        self.build_tab(self.tab_computer_book, "computers", "Computers")
        self.build_tab(self.tab_admin, "admin", "Admin")
        self.build_reminder_tab(self.tab_reminders)
        self.build_settings_tab(self.tab_settings)

    def build_tab(self, parent, category_key, category_label):
        """Create one account-management tab with form, action buttons, and results table."""
        container = ttk.Frame(parent, padding=10)
        container.pack(fill="both", expand=True)

        form_frame = ttk.Frame(container)
        form_frame.pack(fill="x")

        employee_var = tk.StringVar()
        account_var = tk.StringVar()
        username_var = tk.StringVar()
        password_var = tk.StringVar()
        notes_var = tk.StringVar()

        ttk.Label(form_frame, text="Employee Name").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=employee_var, width=30).grid(row=0, column=1, sticky="we", padx=5, pady=5)

        ttk.Label(form_frame, text="Account Name").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=account_var, width=30).grid(row=0, column=3, sticky="we", padx=5, pady=5)

        ttk.Label(form_frame, text="Username").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=username_var, width=30).grid(row=1, column=1, sticky="we", padx=5, pady=5)

        ttk.Label(form_frame, text="Password").grid(row=1, column=2, sticky="w", padx=5, pady=5)
        password_entry = ttk.Entry(form_frame, textvariable=password_var, width=30, show="•")
        password_entry.grid(row=1, column=3, sticky="we", padx=5, pady=5)
        show_password_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form_frame,
            text="Show",
            variable=show_password_var,
            command=lambda entry=password_entry, flag=show_password_var: entry.configure(
                show="" if flag.get() else "•"
            ),
        ).grid(row=1, column=4, sticky="w", padx=5, pady=5)

        ttk.Label(form_frame, text="Notes").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(form_frame, textvariable=notes_var, width=90).grid(row=2, column=1, columnspan=3, sticky="we", padx=5, pady=5)

        for col in range(4):
            form_frame.columnconfigure(col, weight=1)

        button_frame = ttk.Frame(container)
        button_frame.pack(fill="x", pady=(6, 8))

        ttk.Button(button_frame, text="Add", command=lambda key=category_key: self.add_record(key)).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Update", command=lambda key=category_key: self.update_record(key)).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Delete", command=lambda key=category_key: self.delete_record(key)).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Search", command=lambda key=category_key: self.search_records(key)).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Clear", command=lambda key=category_key: self.clear_fields(key)).pack(side="left", padx=4)
        ttk.Button(
            button_frame,
            text="Generate Password",
            command=lambda key=category_key: self.generate_and_fill_password(key),
        ).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Import", command=lambda key=category_key: self.import_records(key)).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Export", command=lambda key=category_key: self.export_records(key)).pack(side="left", padx=4)
        ttk.Button(
            button_frame,
            text="Template Export",
            command=lambda key=category_key: self.export_template_records(key),
        ).pack(side="left", padx=4)

        storage_type = "Encrypted local vault"
        ttk.Label(button_frame, text=f"{category_label} | Storage: {storage_type}").pack(side="right", padx=4)

        columns = ("employee_name", "account_name", "username", "account_password", "notes")
        tree = ttk.Treeview(container, columns=columns, show="headings", height=16)
        tree.heading("employee_name", text="Employee Name")
        tree.heading("account_name", text="Account Name")
        tree.heading("username", text="Username")
        tree.heading("account_password", text="Password")
        tree.heading("notes", text="Notes")

        tree.column("employee_name", width=220, anchor="w")
        tree.column("account_name", width=220, anchor="w")
        tree.column("username", width=220, anchor="w")
        tree.column("account_password", width=220, anchor="w")
        tree.column("notes", width=360, anchor="w")

        y_scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)

        tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")

        tree.bind("<<TreeviewSelect>>", lambda _event, key=category_key: self.on_tree_select(key))

        self.tabs[category_key] = {
            "employee_var": employee_var,
            "account_var": account_var,
            "username_var": username_var,
            "password_var": password_var,
            "notes_var": notes_var,
            "password_entry": password_entry,
            "show_password_var": show_password_var,
            "tree": tree,
            "selected_id": None,
        }

    def build_reminder_tab(self, parent):
        """Create the dedicated reminder tab listing exact overdue records."""
        container = ttk.Frame(parent, padding=10)
        container.pack(fill="both", expand=True)

        top_bar = ttk.Frame(container)
        top_bar.pack(fill="x", pady=(0, 8))

        ttk.Label(
            top_bar,
            text="Passwords listed below are overdue for update (90+ days since last update).",
        ).pack(side="left", padx=4)

        ttk.Button(top_bar, text="Refresh", command=self.refresh_reminder_tab).pack(side="right", padx=4)
        ttk.Button(top_bar, text="Export All", command=self.export_all_records).pack(side="right", padx=4)
        ttk.Button(top_bar, text="Import All", command=self.import_all_records).pack(side="right", padx=4)
        ttk.Button(top_bar, text="Template All", command=self.export_all_template_records).pack(side="right", padx=4)

        columns = ("category", "employee_name", "account_name", "username", "updated_at", "days_since_update")
        self.reminder_tree = ttk.Treeview(container, columns=columns, show="headings", height=20)
        self.reminder_tree.heading("category", text="Category")
        self.reminder_tree.heading("employee_name", text="Employee Name")
        self.reminder_tree.heading("account_name", text="Account Name")
        self.reminder_tree.heading("username", text="Username")
        self.reminder_tree.heading("updated_at", text="Last Updated")
        self.reminder_tree.heading("days_since_update", text="Days Since Update")

        self.reminder_tree.column("category", width=170, anchor="w")
        self.reminder_tree.column("employee_name", width=210, anchor="w")
        self.reminder_tree.column("account_name", width=210, anchor="w")
        self.reminder_tree.column("username", width=210, anchor="w")
        self.reminder_tree.column("updated_at", width=230, anchor="w")
        self.reminder_tree.column("days_since_update", width=180, anchor="center")

        y_scroll = ttk.Scrollbar(container, orient="vertical", command=self.reminder_tree.yview)
        self.reminder_tree.configure(yscrollcommand=y_scroll.set)

        self.reminder_tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")

    def load_all_tabs(self):
        """Load records into all account tabs."""
        for category_key in self.tabs:
            self.load_tab_data(category_key)

    def load_tab_data(self, category_key, search_filters=None):
        """Populate one account tab Treeview, optionally filtered by supported fields."""
        self.clear_fields(category_key)
        tree = self.tabs[category_key]["tree"]
        for item_id in tree.get_children():
            tree.delete(item_id)

        records = self.storage.fetch_records(category_key, search_filters=search_filters)
        for row in records:
            tree.insert(
                "",
                "end",
                iid=str(row["password_id"]),
                values=(
                    row["employee_name"],
                    row["account_name"],
                    row["username"],
                    "••••••••",
                    row.get("notes") or "",
                ),
            )

    def refresh_reminder_tab(self):
        """Reload reminder tab with all overdue records across categories."""
        if self.reminder_tree is None:
            return

        for item_id in self.reminder_tree.get_children():
            self.reminder_tree.delete(item_id)

        due_records = self.storage.fetch_all_due_password_reminders(days=90)
        for record in due_records:
            self.reminder_tree.insert(
                "",
                "end",
                values=(
                    record["category_label"],
                    record["employee_name"],
                    record["account_name"],
                    record["username"],
                    record["updated_at"],
                    record["days_since_update"],
                ),
            )

    def on_tree_select(self, category_key):
        """Mirror selected row values into the tab form fields."""
        tree = self.tabs[category_key]["tree"]
        selected = tree.selection()
        if not selected:
            self.clear_fields(category_key)
            return

        selected_id = selected[0]
        self.tabs[category_key]["selected_id"] = selected_id
        values = tree.item(selected_id, "values")
        self.tabs[category_key]["show_password_var"].set(False)
        self.tabs[category_key]["password_entry"].configure(show="•")
        try:
            record = self.storage.fetch_record(category_key, int(selected_id))
        except Exception as exc:
            self.handle_ui_exception("Load Error", "Unable to load the selected record.", "select_record", exc)
            self.clear_fields(category_key)
            return
        if not record:
            self.clear_fields(category_key)
            return

        self.tabs[category_key]["employee_var"].set(values[0])
        self.tabs[category_key]["account_var"].set(values[1])
        self.tabs[category_key]["username_var"].set(values[2])
        self.tabs[category_key]["password_var"].set(record["account_password"])
        self.tabs[category_key]["notes_var"].set(values[4])

    def clear_fields(self, category_key):
        """Clear form fields and row selection for one tab."""
        self.tabs[category_key]["employee_var"].set("")
        self.tabs[category_key]["account_var"].set("")
        self.tabs[category_key]["username_var"].set("")
        self.tabs[category_key]["password_var"].set("")
        self.tabs[category_key]["notes_var"].set("")
        self.tabs[category_key]["show_password_var"].set(False)
        self.tabs[category_key]["password_entry"].configure(show="•")
        self.tabs[category_key]["selected_id"] = None

        tree = self.tabs[category_key]["tree"]
        tree.selection_remove(tree.selection())

    def read_form(self, category_key):
        """Read the current tab form into a normalized record payload."""
        employee_name = self.tabs[category_key]["employee_var"].get().strip()
        account_name = self.tabs[category_key]["account_var"].get().strip()
        username = self.tabs[category_key]["username_var"].get().strip()
        account_password = self.tabs[category_key]["password_var"].get().strip()
        notes = self.tabs[category_key]["notes_var"].get().strip()

        return {
            "employee_name": employee_name,
            "account_name": account_name,
            "username": username,
            "account_password": account_password,
            "notes": notes,
        }

    def add_record(self, category_key):
        """Add a new record from the current form values."""
        payload = self.read_form(category_key)
        if not self.validate_required_fields(payload):
            return

        try:
            self.storage.add_record(category_key, payload)
            self.load_tab_data(category_key)
            self.refresh_reminder_tab()
            self.clear_fields(category_key)
            messagebox.showinfo("Added", "Record added successfully.")
        except ValueError as exc:
            messagebox.showwarning("Duplicate", str(exc))
        except Exception as exc:
            self.handle_ui_exception(
                "Error",
                "Failed to add record. Review logs for details.",
                "add_record",
                exc,
            )

    def update_record(self, category_key):
        """Update the selected record using current form values."""
        selected_id = self.tabs[category_key]["selected_id"]
        if not selected_id:
            messagebox.showwarning("Selection Required", "Select a record to update.")
            return

        payload = self.read_form(category_key)
        if not self.validate_required_fields(payload):
            return

        try:
            self.storage.update_record(category_key, int(selected_id), payload)
            self.load_tab_data(category_key)
            self.refresh_reminder_tab()
            self.clear_fields(category_key)
            messagebox.showinfo("Updated", "Record updated successfully.")
        except ValueError as exc:
            messagebox.showwarning("Duplicate", str(exc))
        except Exception as exc:
            self.handle_ui_exception(
                "Error",
                "Failed to update record. Review logs for details.",
                "update_record",
                exc,
            )

    def delete_record(self, category_key):
        """Delete the selected row for the active category tab."""
        selected_id = self.tabs[category_key]["selected_id"]
        if not selected_id:
            messagebox.showwarning("Selection Required", "Select a record to delete.")
            return

        confirmed = messagebox.askokcancel("Confirm Delete", "Delete selected record?")
        if not confirmed:
            return

        try:
            self.storage.delete_record(category_key, int(selected_id))
            self.load_tab_data(category_key)
            self.refresh_reminder_tab()
            self.clear_fields(category_key)
            messagebox.showinfo("Deleted", "Record deleted successfully.")
        except Exception as exc:
            self.handle_ui_exception(
                "Error",
                "Failed to delete record. Review logs for details.",
                "delete_record",
                exc,
            )

    def search_records(self, category_key):
        """Filter one tab by employee name, account name, and username."""
        search_filters = {
            "employee_name": self.tabs[category_key]["employee_var"].get().strip(),
            "account_name": self.tabs[category_key]["account_var"].get().strip(),
            "username": self.tabs[category_key]["username_var"].get().strip(),
        }
        self.clear_fields(category_key)
        self.load_tab_data(category_key, search_filters=search_filters)

    def generate_and_fill_password(self, category_key):
        """Generate a password and pre-fill the password entry field."""
        try:
            generated_password = password_generator.generate_password()
        except Exception as exc:
            self.handle_ui_exception(
                "Generator Error",
                "Unable to generate a password with current settings.",
                "generate_password",
                exc,
            )
            return

        self.tabs[category_key]["password_var"].set(generated_password)

    def import_records(self, category_key):
        """Import records into one category from an encrypted vault backup or tabular file."""
        file_path = filedialog.askopenfilename(
            title="Import Password Data",
            filetypes=[
                ("Supported files", "*.vault *.csv *.xlsx"),
                ("Encrypted vault files", "*.vault"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            imported, skipped = self.storage.import_records_from_file(category_key, file_path)
            self.load_tab_data(category_key)
            self.refresh_reminder_tab()
            messagebox.showinfo(
                "Import Complete",
                f"Imported or updated: {imported}\nSkipped invalid rows: {skipped}",
            )
        except Exception as exc:
            self.handle_ui_exception(
                "Import Error",
                "Failed to import records. Confirm file format and check logs.",
                "import_records",
                exc,
            )

    def export_records(self, category_key):
        """Export one category to an encrypted vault backup."""
        default_name = f"{category_key}_backup"
        file_path = filedialog.asksaveasfilename(
            title="Export Password Data",
            defaultextension=".vault",
            initialfile=default_name,
            filetypes=[
                ("Encrypted vault files", "*.vault"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            self.storage.export_records_to_file(category_key, file_path)
            messagebox.showinfo("Export Complete", f"Backup saved to:\n{file_path}")
        except Exception as exc:
            self.handle_ui_exception(
                "Export Error",
                "Failed to export records. Check logs for details.",
                "export_records",
                exc,
            )

    def export_template_records(self, category_key):
        """Export header-only CSV/XLSX template for one category."""
        default_name = f"{category_key}_template"
        file_path = filedialog.asksaveasfilename(
            title="Export Category Template",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            self.storage.export_template_to_file(category_key, file_path)
            messagebox.showinfo("Template Export Complete", f"Template saved to:\n{file_path}")
        except Exception as exc:
            self.handle_ui_exception(
                "Template Export Error",
                "Failed to export template. Check logs for details.",
                "export_template_records",
                exc,
            )

    def import_all_records(self):
        """Import all categories from an encrypted vault backup or tabular file."""
        file_path = filedialog.askopenfilename(
            title="Import Full Backup",
            filetypes=[
                ("Supported files", "*.vault *.csv *.xlsx"),
                ("Encrypted vault files", "*.vault"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            summary = self.storage.import_all_records_from_file(file_path)
            self.load_all_tabs()
            self.refresh_reminder_tab()
            messagebox.showinfo(
                "Import Complete",
                (
                    "Imported/updated by category:\n"
                    f"Password Book: {summary['password_book']}\n"
                    f"Mobile Devices: {summary['mobile_devices']}\n"
                    f"Computers: {summary['computers']}\n"
                    f"Admin: {summary['admin']}"
                ),
            )
        except Exception as exc:
            self.handle_ui_exception(
                "Import Error",
                "Failed to import backup. Confirm file format and check logs.",
                "import_all_records",
                exc,
            )

    def export_all_records(self):
        """Export all categories to one encrypted vault backup."""
        file_path = filedialog.asksaveasfilename(
            title="Export Full Backup",
            defaultextension=".vault",
            initialfile="password_manager_full_backup",
            filetypes=[
                ("Encrypted vault files", "*.vault"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            self.storage.export_all_records_to_file(file_path)
            messagebox.showinfo("Export Complete", f"Full backup saved to:\n{file_path}")
        except Exception as exc:
            self.handle_ui_exception(
                "Export Error",
                "Failed to export backup. Check logs for details.",
                "export_all_records",
                exc,
            )

    def export_all_template_records(self):
        """Export header-only CSV/XLSX template for full multi-category imports."""
        file_path = filedialog.asksaveasfilename(
            title="Export Full Template",
            defaultextension=".csv",
            initialfile="password_manager_full_template",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            self.storage.export_all_template_to_file(file_path)
            messagebox.showinfo("Template Export Complete", f"Template saved to:\n{file_path}")
        except Exception as exc:
            self.handle_ui_exception(
                "Template Export Error",
                "Failed to export template. Check logs for details.",
                "export_all_template_records",
                exc,
            )

    def validate_required_fields(self, payload):
        """Validate required fields before add/update operations."""
        required = ["employee_name", "account_name", "username", "account_password"]
        missing = [field for field in required if not payload[field]]
        if missing:
            messagebox.showwarning(
                "Required Fields",
                "Please complete: " + ", ".join(missing),
            )
            return False
        return True

    def check_password_reminders(self):
        """Show a startup popup summary for overdue password updates."""
        due_records = self.storage.fetch_all_due_password_reminders(days=90)
        if not due_records:
            return

        counts = {label: 0 for label in CATEGORY_LABELS.values()}
        for row in due_records:
            counts[row["category_label"]] += 1

        summary_lines = [f"{label}: {counts[label]} due" for label in CATEGORY_LABELS.values()]

        messagebox.showwarning(
            "Password Update Reminder",
            "Passwords due for update (90+ days):\n" + "\n".join(summary_lines),
        )

    def build_settings_tab(self, parent):
        """Create settings controls for password generation behavior."""
        container = ttk.Frame(parent, padding=12)
        container.pack(fill="both", expand=True)

        form = ttk.LabelFrame(container, text="⚙️ Settings", padding=12)
        form.pack(fill="x", pady=(0, 10))

        self.settings_vars = {
            "format": tk.StringVar(value="scrambled"),
            "word_count": tk.StringVar(value="2"),
            "numbers_count": tk.StringVar(value="2"),
            "symbols_count": tk.StringVar(value="1"),
            "letters_count": tk.StringVar(value="12"),
            "capitalize_words": tk.BooleanVar(value=True),
        }

        ttk.Label(form, text="Format").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        format_combo = ttk.Combobox(
            form,
            textvariable=self.settings_vars["format"],
            state="readonly",
            values=("word_symbol_word_numbers", "word_number_chunks", "scrambled"),
            width=28,
        )
        format_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        format_combo.bind("<<ComboboxSelected>>", lambda _event: self._toggle_settings_fields())

        ttk.Label(form, text="Words").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.words_entry = ttk.Entry(form, textvariable=self.settings_vars["word_count"], width=12)
        self.words_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Numbers").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.numbers_entry = ttk.Entry(form, textvariable=self.settings_vars["numbers_count"], width=12)
        self.numbers_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Symbols").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.symbols_entry = ttk.Entry(form, textvariable=self.settings_vars["symbols_count"], width=12)
        self.symbols_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Scrambled Letters").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.letters_entry = ttk.Entry(form, textvariable=self.settings_vars["letters_count"], width=12)
        self.letters_entry.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        self.capitalize_check = ttk.Checkbutton(
            form,
            text="Capitalize Words",
            variable=self.settings_vars["capitalize_words"],
        )
        self.capitalize_check.grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 5))

        help_text = (
            "Format examples:\n"
            "- word_symbol_word_numbers: Word;Word75\n"
            "- word_number_chunks: Word76Word64word23\n"
            "- scrambled: wd}o75(rrod$w8"
        )
        ttk.Label(form, text=help_text, justify="left").grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 0))

        button_bar = ttk.Frame(container)
        button_bar.pack(fill="x", pady=(4, 6))

        ttk.Button(button_bar, text="Save Settings", command=self.save_settings_from_form).pack(side="left", padx=4)
        ttk.Button(button_bar, text="Reload", command=self.load_settings_form).pack(side="left", padx=4)
        ttk.Button(button_bar, text="Generate Preview", command=self.generate_settings_preview).pack(side="left", padx=4)

        ttk.Label(button_bar, textvariable=self.settings_status_var).pack(side="right", padx=4)

        preview_frame = ttk.LabelFrame(container, text="Preview", padding=10)
        preview_frame.pack(fill="x")
        self.settings_preview_var = tk.StringVar(value="")
        ttk.Entry(preview_frame, textvariable=self.settings_preview_var, width=70, state="readonly").pack(fill="x", padx=4, pady=4)

        self.load_settings_form()

    def _toggle_settings_fields(self):
        """Enable or disable fields based on selected password format."""
        selected_format = self.settings_vars["format"].get()
        is_scrambled = selected_format == "scrambled"

        self.words_entry.configure(state="disabled" if is_scrambled else "normal")
        self.capitalize_check.configure(state="disabled" if is_scrambled else "normal")
        self.letters_entry.configure(state="normal" if is_scrambled else "disabled")

    def load_settings_form(self):
        """Load persisted generator settings into the Settings tab form."""
        settings = password_generator.get_password_settings()
        self.settings_vars["format"].set(settings["format"])
        self.settings_vars["word_count"].set(str(settings["word_count"]))
        self.settings_vars["numbers_count"].set(str(settings["numbers_count"]))
        self.settings_vars["symbols_count"].set(str(settings["symbols_count"]))
        self.settings_vars["letters_count"].set(str(settings["letters_count"]))
        self.settings_vars["capitalize_words"].set(bool(settings["capitalize_words"]))
        self.settings_status_var.set("Settings loaded")
        self._toggle_settings_fields()

    def save_settings_from_form(self):
        """Validate and persist generator settings from the UI form."""
        try:
            payload = {
                "format": self.settings_vars["format"].get(),
                "word_count": int(self.settings_vars["word_count"].get().strip()),
                "numbers_count": int(self.settings_vars["numbers_count"].get().strip()),
                "symbols_count": int(self.settings_vars["symbols_count"].get().strip()),
                "letters_count": int(self.settings_vars["letters_count"].get().strip()),
                "capitalize_words": bool(self.settings_vars["capitalize_words"].get()),
            }
        except ValueError:
            messagebox.showerror("Invalid Settings", "Word, number, symbol, and letter counts must be integers.")
            return

        if payload["word_count"] <= 0:
            messagebox.showerror("Invalid Settings", "Word count must be greater than 0.")
            return
        if payload["numbers_count"] < 0 or payload["symbols_count"] < 0:
            messagebox.showerror("Invalid Settings", "Numbers and symbols must be 0 or greater.")
            return
        if payload["letters_count"] <= 0:
            messagebox.showerror("Invalid Settings", "Scrambled letters must be greater than 0.")
            return

        try:
            saved = password_generator.update_password_settings(payload)
        except Exception as exc:
            self.handle_ui_exception(
                "Save Failed",
                "Unable to save settings. Check values and review logs.",
                "save_settings",
                exc,
            )
            return

        self.settings_status_var.set("Settings saved")
        self.load_settings_form()
        messagebox.showinfo("Settings Saved", f"Generator format set to: {saved['format']}")

    def generate_settings_preview(self):
        """Generate a one-click preview using current stored settings."""
        try:
            preview = password_generator.generate_password()
        except Exception as exc:
            self.handle_ui_exception(
                "Preview Error",
                "Unable to generate preview with current settings.",
                "generate_preview",
                exc,
            )
            return
        self.settings_preview_var.set(preview)


class StorageManager:
    """Encrypted local persistence for the first, single-owner release."""

    def __init__(self, master_password):
        """Prepare the local vault without silently falling back to plaintext."""
        self.base_dir = BASE_DIR
        self.master_password = master_password
        self.vault_path = os.path.join(self.base_dir, "json_files", "password_data.vault")
        self.legacy_json_store_path = os.path.join(self.base_dir, "json_files", "password_data.json")
        self.json_store_path = self.vault_path
        self.table_map = {
            "password_book": "password_manager",
            "mobile_devices": "password_manager_mobile_devices",
            "computers": "password_manager_computers",
            "admin": "password_manager_admin",
        }
        self.use_database = False
        self.fallback_warning = ""

        self._initialize_storage()

    def _initialize_storage(self):
        """Create an encrypted vault, refusing to consume a legacy plaintext file."""
        if os.path.exists(self.legacy_json_store_path):
            raise VaultCryptoError(
                "A legacy plaintext password_data.json exists. Move it aside and review it manually; "
                "this app will not read plaintext credentials automatically."
            )
        self._ensure_json_store_exists()
        LOGGER.info("storage_backend_selected backend=encrypted_local_vault")

    def _create_table_sql(self, table_name):
        """Return table DDL aligned with project SQL schema naming."""
        return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            password_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            employee_name VARCHAR(255) NOT NULL,
            account_name VARCHAR(255) NOT NULL,
            username VARCHAR(255) NOT NULL,
            account_password TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_{table_name}_account UNIQUE(employee_name, account_name, username)
        );
        """

    def _ensure_json_store_exists(self):
        """Create or validate the encrypted local vault."""
        if not os.path.exists(self.json_store_path):
            seed = {
                "password_book": [],
                "mobile_devices": [],
                "computers": [],
                "admin": [],
                "next_id": 1,
            }
            save_encrypted_file(self.json_store_path, seed, self.master_password)
            return

        existing = load_encrypted_file(self.json_store_path, self.master_password)
        if not isinstance(existing, dict):
            raise VaultCryptoError("The encrypted vault payload is invalid.")

        changed = False
        for category_key in CATEGORY_LABELS:
            if category_key not in existing:
                existing[category_key] = []
                changed = True

        if "next_id" not in existing:
            existing["next_id"] = 1
            changed = True

        self._validate_json_payload(existing)

        if changed:
            self._save_json(existing)

    def _validate_json_payload(self, payload):
        """Validate vault records and reject duplicate or unsafe IDs."""
        seen_ids = set()
        max_id = 0
        required_fields = ("employee_name", "account_name", "username", "account_password")

        for category_key in CATEGORY_LABELS:
            records = payload.get(category_key)
            if not isinstance(records, list):
                raise VaultCryptoError("The encrypted vault contains an invalid category.")

            for record in records:
                if not isinstance(record, dict):
                    raise VaultCryptoError("The encrypted vault contains an invalid record.")
                raw_id = record.get("password_id")
                if type(raw_id) is not int or raw_id <= 0:
                    raise VaultCryptoError("The encrypted vault contains an invalid record ID.")
                password_id = raw_id
                if password_id in seen_ids:
                    raise VaultCryptoError(
                        "The encrypted vault contains duplicate record IDs. Restore a clean backup."
                    )
                seen_ids.add(password_id)
                max_id = max(max_id, password_id)
                for field in required_fields:
                    value = record.get(field)
                    if not isinstance(value, str) or not value.strip():
                        raise VaultCryptoError("The encrypted vault contains an invalid record.")

        next_id = payload.get("next_id")
        if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id <= max_id:
            raise VaultCryptoError("The encrypted vault has an invalid next record ID.")

    def _load_json(self):
        """Load and decrypt the local vault payload."""
        self._ensure_json_store_exists()
        return load_encrypted_file(self.json_store_path, self.master_password)

    def _save_json(self, payload):
        """Persist the local vault with authenticated encryption and atomic replacement."""
        save_encrypted_file(self.json_store_path, payload, self.master_password)

    def fetch_records(self, category_key, search_filters=None):
        """Fetch records by category, optionally filtered by supported text fields."""
        if self.use_database:
            return self._db_fetch_records(category_key, search_filters)
        return self._json_fetch_records(category_key, search_filters)

    def fetch_record(self, category_key, password_id):
        """Fetch one record only after the encrypted vault has been unlocked."""
        for record in self.fetch_records(category_key):
            if int(record.get("password_id")) == int(password_id):
                return record
        return None

    def add_record(self, category_key, payload):
        """Add one record to selected category."""
        if self.use_database:
            self._db_add_record(category_key, payload)
            return
        self._json_add_record(category_key, payload)

    def update_record(self, category_key, password_id, payload):
        """Update one record by id in selected category."""
        if self.use_database:
            self._db_update_record(category_key, password_id, payload)
            return
        self._json_update_record(category_key, password_id, payload)

    def delete_record(self, category_key, password_id):
        """Delete one record by id in selected category."""
        if self.use_database:
            self._db_delete_record(category_key, password_id)
            return
        self._json_delete_record(category_key, password_id)

    def fetch_all_due_password_reminders(self, days=90):
        """Return exact overdue records across all categories for reminder tab display."""
        all_due = []

        for category_key, label in CATEGORY_LABELS.items():
            records = self.fetch_records(category_key)
            threshold = datetime.now() - timedelta(days=days)

            for record in records:
                updated_at = self._parse_record_datetime(record.get("updated_at"), record.get("created_at"))
                if not updated_at or updated_at > threshold:
                    continue

                all_due.append(
                    {
                        "category_key": category_key,
                        "category_label": label,
                        "password_id": record.get("password_id"),
                        "employee_name": record.get("employee_name", ""),
                        "account_name": record.get("account_name", ""),
                        "username": record.get("username", ""),
                        "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "days_since_update": (datetime.now() - updated_at).days,
                    }
                )

        return sorted(
            all_due,
            key=lambda row: (row["category_label"], row["employee_name"].lower(), row["account_name"].lower()),
        )

    def export_records_to_file(self, category_key, file_path):
        """Export one category only as an encrypted vault backup."""
        records = [self._serialize_record(row) for row in self.fetch_records(category_key)]
        ext = self._file_extension(file_path)
        if ext != ".vault":
            raise ValueError("Password backups must use the encrypted .vault format.")
        save_encrypted_file(
            file_path,
            {category_key: records, "exported_at": datetime.now().isoformat(timespec="seconds")},
            self.master_password,
        )

    def export_template_to_file(self, category_key, file_path):
        """Export a header-only CSV/XLSX template for one category."""
        _ = category_key
        ext = self._file_extension(file_path)
        if ext not in (".csv", ".xlsx"):
            raise ValueError("Template export supports .csv or .xlsx only.")
        self._write_tabular_file(file_path, rows=[], include_category=False)

    def export_all_records_to_file(self, file_path):
        """Export all categories only as one encrypted vault backup."""
        ext = self._file_extension(file_path)
        if ext != ".vault":
            raise ValueError("Password backups must use the encrypted .vault format.")
        payload = {
            category_key: [self._serialize_record(row) for row in self.fetch_records(category_key)]
            for category_key in CATEGORY_LABELS
        }
        payload["exported_at"] = datetime.now().isoformat(timespec="seconds")
        save_encrypted_file(file_path, payload, self.master_password)

    def export_all_template_to_file(self, file_path):
        """Export a header-only CSV/XLSX template for full category imports."""
        ext = self._file_extension(file_path)
        if ext not in (".csv", ".xlsx"):
            raise ValueError("Template export supports .csv or .xlsx only.")
        self._write_tabular_file(file_path, rows=[], include_category=True)

    def import_records_from_file(self, category_key, file_path):
        """Import one category from an encrypted vault backup or tabular file."""
        ext = self._file_extension(file_path)
        if ext == ".vault":
            payload = load_encrypted_file(file_path, self.master_password)

            if isinstance(payload, list):
                records = payload
            elif isinstance(payload, dict) and isinstance(payload.get(category_key), list):
                records = payload[category_key]
            elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
                records = payload["records"]
            else:
                raise ValueError("Import JSON must be a record list or include the selected category key.")
            self._validate_import_record_ids(records)
            return self._import_records(category_key, records, enforce_category=True)

        if ext == ".json":
            raise ValueError("Plaintext JSON imports are disabled. Use an encrypted .vault backup.")

        rows = self._read_tabular_file(file_path)
        self._validate_import_record_ids(rows)
        return self._import_records(category_key, rows, enforce_category=True)

    def import_all_records_from_file(self, file_path):
        """Import all categories from an encrypted vault backup or tabular file."""
        ext = self._file_extension(file_path)

        if ext == ".vault":
            payload = load_encrypted_file(file_path, self.master_password)

            if isinstance(payload, dict):
                if isinstance(payload.get("records"), list):
                    return self._import_full_rows(payload["records"], require_category=True)

                category_keys_present = [
                    category_key for category_key in CATEGORY_LABELS if category_key in payload
                ]
                if not category_keys_present:
                    if "records" in payload:
                        raise ValueError("Full import records must be a list.")
                    raise ValueError(
                        "Encrypted vault does not contain any recognized password categories "
                        "or a records list."
                    )

                for category_key in CATEGORY_LABELS:
                    if category_key not in payload:
                        continue
                    records = payload[category_key]
                    if not isinstance(records, list):
                        raise ValueError("Full import category values must be lists.")
                return self._import_full_category_payload(payload)

            if isinstance(payload, list):
                return self._import_full_rows(payload, require_category=True)

            raise ValueError("Unsupported encrypted vault structure for full import.")

        if ext == ".json":
            raise ValueError("Plaintext JSON imports are disabled. Use an encrypted .vault backup.")

        rows = self._read_tabular_file(file_path)
        return self._import_full_rows(rows, require_category=True)

    def _import_full_category_payload(self, payload):
        """Validate and atomically import a category-keyed backup payload."""
        grouped_rows = {category_key: [] for category_key in CATEGORY_LABELS}
        seen_ids = set()
        for category_key in CATEGORY_LABELS:
            records = payload.get(category_key, [])
            if not isinstance(records, list):
                raise ValueError("Full import category values must be lists.")
            self._validate_import_rows(
                records,
                require_category=False,
                expected_category=category_key,
                seen_ids=seen_ids,
            )
            grouped_rows[category_key] = records
        return self._import_grouped_rows_atomically(grouped_rows)

    def _import_full_rows(self, rows, require_category):
        """Validate every full-import row before changing storage, then import once."""
        self._validate_import_rows(rows, require_category=require_category)
        grouped_rows = self._group_rows_by_category(rows)
        return self._import_grouped_rows_atomically(grouped_rows)

    def _validate_import_rows(self, records, require_category, expected_category=None, seen_ids=None):
        """Reject malformed full-import rows before any record can be written."""
        self._validate_import_record_ids(records, seen_ids=seen_ids)
        category_key_by_label = {label.lower(): key for key, label in CATEGORY_LABELS.items()}
        for row in records:
            if not isinstance(row, dict):
                raise ValueError("Full imports require valid records with all required fields.")
            canonical = self._canonicalize_row_keys(row)
            if require_category:
                category_value = str(canonical.get("category", "")).strip().lower()
                row_category = category_key_by_label.get(category_value, category_value)
                if row_category not in CATEGORY_LABELS:
                    raise ValueError("Full imports require a valid Category for every row.")
            elif expected_category and canonical.get("category") not in (None, ""):
                category_value = str(canonical.get("category", "")).strip().lower()
                row_category = category_key_by_label.get(category_value, category_value)
                if row_category != expected_category:
                    raise ValueError("A category-keyed import row does not match its category.")
            if self._normalize_import_row(row) is None:
                raise ValueError("Full imports require Employee Name, Account Name, Username, and Password.")

    def _import_grouped_rows_atomically(self, grouped_rows):
        """Apply a validated local-vault import in memory and persist it with one save."""
        if self.use_database:
            summary = {category_key: 0 for category_key in CATEGORY_LABELS}
            for category_key, records in grouped_rows.items():
                imported, _skipped = self._import_records(
                    category_key, records, enforce_category=True
                )
                summary[category_key] = imported
            return summary

        data = self._load_json()
        summary = {category_key: 0 for category_key in CATEGORY_LABELS}
        for category_key, records in grouped_rows.items():
            for row in records:
                normalized = self._normalize_import_row(row)
                self._json_upsert_record_in_data(data, category_key, normalized)
                summary[category_key] += 1
        self._save_json(data)
        return summary

    def _import_records(self, category_key, records, enforce_category=False):
        """Validate and import rows with upsert behavior by employee/account/username."""
        self._validate_import_record_ids(records)
        imported = 0
        skipped = 0

        for row in records:
            if enforce_category and isinstance(row, dict):
                canonical = self._canonicalize_row_keys(row)
                category_value = str(canonical.get("category", "")).strip().lower()
                if category_value:
                    category_key_by_label = {
                        label.lower(): key for key, label in CATEGORY_LABELS.items()
                    }
                    row_category = category_key_by_label.get(category_value, category_value)
                    if row_category not in CATEGORY_LABELS or row_category != category_key:
                        skipped += 1
                        continue
            normalized = self._normalize_import_row(row)
            if not normalized:
                skipped += 1
                continue
            self._upsert_record(category_key, normalized)
            imported += 1

        return imported, skipped

    def _validate_import_record_ids(self, records, seen_ids=None):
        """Reject duplicate or malformed IDs supplied by an imported backup."""
        seen_ids = seen_ids if seen_ids is not None else set()
        for row in records:
            if not isinstance(row, dict):
                continue
            canonical = self._canonicalize_row_keys(row)
            raw_id = canonical.get("password_id")
            if raw_id in (None, ""):
                continue
            if isinstance(raw_id, bool):
                raise VaultCryptoError("The imported backup contains an invalid record ID.")
            if type(raw_id) is int:
                password_id = raw_id
            elif isinstance(raw_id, str) and re.fullmatch(r"[1-9][0-9]*", raw_id.strip()):
                try:
                    password_id = int(raw_id.strip())
                except ValueError as exc:
                    raise VaultCryptoError(
                        "The imported backup contains an invalid record ID."
                    ) from exc
            else:
                raise VaultCryptoError("The imported backup contains an invalid record ID.")
            if password_id <= 0:
                raise VaultCryptoError("The imported backup contains an invalid record ID.")
            if password_id in seen_ids:
                raise VaultCryptoError(
                    "The imported backup contains duplicate record IDs. Restore a clean backup."
                )
            seen_ids.add(password_id)

    def _validate_full_import_categories(self, records):
        """Reject full-import rows that cannot be routed to a known category."""
        category_key_by_label = {label.lower(): key for key, label in CATEGORY_LABELS.items()}
        for row in records:
            if not isinstance(row, dict):
                raise ValueError("Full imports require a valid Category for every row.")
            canonical = self._canonicalize_row_keys(row)
            category_value = str(canonical.get("category", "")).strip().lower()
            row_category = category_key_by_label.get(category_value, category_value)
            if row_category not in CATEGORY_LABELS:
                raise ValueError("Full imports require a valid Category for every row.")

    def _upsert_record(self, category_key, row):
        """Insert or update a row depending on backend and uniqueness tuple."""
        if self.use_database:
            self._db_upsert_record(category_key, row)
        else:
            self._json_upsert_record(category_key, row)

    def _db_fetch_records(self, category_key, search_filters):
        """Fetch category records from PostgreSQL using optional field filters."""
        table_name = self.table_map[category_key]
        search_filters = search_filters or {}
        employee_filter = f"%{str(search_filters.get('employee_name', '')).lower()}%"
        account_filter = f"%{str(search_filters.get('account_name', '')).lower()}%"
        username_filter = f"%{str(search_filters.get('username', '')).lower()}%"
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        password_id,
                        employee_name,
                        account_name,
                        username,
                        account_password,
                        COALESCE(notes, ''),
                        created_at,
                        updated_at
                    FROM {table_name}
                                        WHERE LOWER(employee_name) LIKE %s
                                            AND LOWER(account_name) LIKE %s
                                            AND LOWER(username) LIKE %s
                    ORDER BY employee_name, account_name, username;
                    """,
                                        (employee_filter, account_filter, username_filter),
                )
                rows = cursor.fetchall()

        return [
            {
                "password_id": row[0],
                "employee_name": row[1],
                "account_name": row[2],
                "username": row[3],
                "account_password": row[4],
                "notes": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def _db_add_record(self, category_key, payload):
        """Insert new PostgreSQL row and raise friendly message on uniqueness conflict."""
        table_name = self.table_map[category_key]
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {table_name}
                        (employee_name, account_name, username, account_password, notes)
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (
                            payload["employee_name"],
                            payload["account_name"],
                            payload["username"],
                            payload["account_password"],
                            payload["notes"],
                        ),
                    )
                conn.commit()
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise ValueError("A record with this employee/account/username already exists.") from exc
            raise

    def _db_update_record(self, category_key, password_id, payload):
        """Update PostgreSQL row by id and refresh updated timestamp."""
        table_name = self.table_map[category_key]
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        UPDATE {table_name}
                        SET
                            employee_name = %s,
                            account_name = %s,
                            username = %s,
                            account_password = %s,
                            notes = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE password_id = %s;
                        """,
                        (
                            payload["employee_name"],
                            payload["account_name"],
                            payload["username"],
                            payload["account_password"],
                            payload["notes"],
                            password_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("The selected record no longer exists.")
                conn.commit()
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise ValueError("A record with this employee/account/username already exists.") from exc
            raise

    def _db_delete_record(self, category_key, password_id):
        """Delete PostgreSQL row by id."""
        table_name = self.table_map[category_key]
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table_name} WHERE password_id = %s;", (password_id,))
            conn.commit()

    def _db_upsert_record(self, category_key, row):
        """Upsert one PostgreSQL row based on unique employee/account/username tuple."""
        table_name = self.table_map[category_key]
        created_at = self._parse_record_datetime(row.get("created_at"), None) or datetime.now()
        updated_at = self._parse_record_datetime(row.get("updated_at"), row.get("created_at")) or datetime.now()

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {table_name}
                    (employee_name, account_name, username, account_password, notes, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT uq_{table_name}_account
                    DO UPDATE SET
                        account_password = EXCLUDED.account_password,
                        notes = EXCLUDED.notes,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (
                        row["employee_name"],
                        row["account_name"],
                        row["username"],
                        row["account_password"],
                        row.get("notes", ""),
                        created_at,
                        updated_at,
                    ),
                )
            conn.commit()

    def _json_fetch_records(self, category_key, search_filters):
        """Fetch category rows from JSON fallback using optional field filters."""
        data = self._load_json()
        all_records = data.get(category_key, [])
        search_filters = search_filters or {}
        employee_filter = str(search_filters.get("employee_name", "")).lower()
        account_filter = str(search_filters.get("account_name", "")).lower()
        username_filter = str(search_filters.get("username", "")).lower()

        filtered = []
        for record in all_records:
            employee_name = record.get("employee_name", "").lower()
            account_name = record.get("account_name", "").lower()
            username = record.get("username", "").lower()

            if employee_filter and employee_filter not in employee_name:
                continue
            if account_filter and account_filter not in account_name:
                continue
            if username_filter and username_filter not in username:
                continue

            filtered.append(record)

        return sorted(
            filtered,
            key=lambda row: (
                row.get("employee_name", "").lower(),
                row.get("account_name", "").lower(),
                row.get("username", "").lower(),
            ),
        )

    def _json_add_record(self, category_key, payload):
        """Insert one row into JSON fallback storage."""
        data = self._load_json()
        records = data[category_key]
        self._json_ensure_not_duplicate(records, payload)

        now = datetime.now().isoformat(timespec="seconds")
        new_record = {
            "password_id": data["next_id"],
            "employee_name": payload["employee_name"],
            "account_name": payload["account_name"],
            "username": payload["username"],
            "account_password": payload["account_password"],
            "notes": payload["notes"],
            "created_at": now,
            "updated_at": now,
        }
        records.append(new_record)
        data["next_id"] += 1
        self._save_json(data)

    def _json_update_record(self, category_key, password_id, payload):
        """Update one JSON fallback row by id."""
        data = self._load_json()
        records = data[category_key]

        target = None
        for record in records:
            if int(record["password_id"]) == int(password_id):
                target = record
                break

        if not target:
            raise ValueError("The selected record no longer exists.")

        self._json_ensure_not_duplicate(records, payload, exclude_id=password_id)

        target["employee_name"] = payload["employee_name"]
        target["account_name"] = payload["account_name"]
        target["username"] = payload["username"]
        target["account_password"] = payload["account_password"]
        target["notes"] = payload["notes"]
        target["updated_at"] = datetime.now().isoformat(timespec="seconds")

        self._save_json(data)

    def _json_delete_record(self, category_key, password_id):
        """Delete one JSON fallback row by id."""
        data = self._load_json()
        records = data[category_key]
        matches = [
            index for index, record in enumerate(records)
            if int(record["password_id"]) == int(password_id)
        ]
        if not matches:
            raise ValueError("The selected record no longer exists.")
        if len(matches) > 1:
            raise VaultCryptoError(
                "The encrypted vault contains duplicate record IDs. Restore a clean backup."
            )
        del records[matches[0]]
        self._save_json(data)

    def _json_upsert_record(self, category_key, row):
        """Upsert one JSON fallback row based on employee/account/username tuple."""
        data = self._load_json()
        self._json_upsert_record_in_data(data, category_key, row)
        self._save_json(data)

    def _json_upsert_record_in_data(self, data, category_key, row):
        """Upsert a row into an already-loaded payload without persisting it."""
        records = data[category_key]

        target = None
        for record in records:
            if (
                record.get("employee_name", "").lower() == row["employee_name"].lower()
                and record.get("account_name", "").lower() == row["account_name"].lower()
                and record.get("username", "").lower() == row["username"].lower()
            ):
                target = record
                break

        if target:
            target["account_password"] = row["account_password"]
            target["notes"] = row.get("notes", "")
            target["updated_at"] = (
                self._parse_record_datetime(row.get("updated_at"), row.get("created_at")) or datetime.now()
            ).isoformat(timespec="seconds")
            return

        now = datetime.now()
        created_at = self._parse_record_datetime(row.get("created_at"), None) or now
        updated_at = self._parse_record_datetime(row.get("updated_at"), row.get("created_at")) or now

        records.append(
            {
                "password_id": data["next_id"],
                "employee_name": row["employee_name"],
                "account_name": row["account_name"],
                "username": row["username"],
                "account_password": row["account_password"],
                "notes": row.get("notes", ""),
                "created_at": created_at.isoformat(timespec="seconds"),
                "updated_at": updated_at.isoformat(timespec="seconds"),
            }
        )
        data["next_id"] += 1

    def _json_ensure_not_duplicate(self, records, payload, exclude_id=None):
        """Enforce uniqueness tuple in JSON fallback mode."""
        new_key = (
            payload["employee_name"].lower(),
            payload["account_name"].lower(),
            payload["username"].lower(),
        )

        for record in records:
            if exclude_id is not None and int(record["password_id"]) == int(exclude_id):
                continue
            current_key = (
                record.get("employee_name", "").lower(),
                record.get("account_name", "").lower(),
                record.get("username", "").lower(),
            )
            if current_key == new_key:
                raise ValueError("A record with this employee/account/username already exists.")

    def _normalize_import_row(self, row):
        """Validate and normalize one imported row into internal field names."""
        if not isinstance(row, dict):
            return None

        canonical = self._canonicalize_row_keys(row)

        employee_name = (
            "" if canonical.get("employee_name") is None
            else str(canonical.get("employee_name")).strip()
        )
        account_name = (
            "" if canonical.get("account_name") is None
            else str(canonical.get("account_name")).strip()
        )
        username = (
            "" if canonical.get("username") is None
            else str(canonical.get("username")).strip()
        )
        account_password = (
            "" if canonical.get("account_password") is None
            else str(canonical.get("account_password")).strip()
        )
        notes = (
            "" if canonical.get("notes") is None
            else str(canonical.get("notes")).strip()
        )

        if not (employee_name and account_name and username and account_password):
            return None

        return {
            "employee_name": employee_name,
            "account_name": account_name,
            "username": username,
            "account_password": account_password,
            "notes": notes,
            "created_at": canonical.get("created_at"),
            "updated_at": canonical.get("updated_at"),
        }

    def _canonicalize_row_keys(self, row):
        """Normalize supported header variants into canonical internal keys."""
        key_map = {
            "employee_name": "employee_name",
            "employee name": "employee_name",
            "account_name": "account_name",
            "account name": "account_name",
            "username": "username",
            "account_password": "account_password",
            "account password": "account_password",
            "password": "account_password",
            "notes": "notes",
            "created_at": "created_at",
            "created at": "created_at",
            "updated_at": "updated_at",
            "updated at": "updated_at",
            "password_id": "password_id",
            "password id": "password_id",
            "category": "category",
        }

        normalized = {}
        for raw_key, value in row.items():
            key = str(raw_key).strip().lower()
            canonical_key = key_map.get(key)
            if canonical_key:
                normalized[canonical_key] = value

        return normalized

    def _group_rows_by_category(self, rows):
        """Group imported rows by category using supported label/key values."""
        grouped = {category_key: [] for category_key in CATEGORY_LABELS}
        label_to_key = {label.lower(): key for key, label in CATEGORY_LABELS.items()}

        for row in rows:
            if not isinstance(row, dict):
                continue
            canonical = self._canonicalize_row_keys(row)
            category_value = str(canonical.get("category", "")).strip().lower()

            if category_value in CATEGORY_LABELS:
                grouped[category_value].append(row)
                continue
            if category_value in label_to_key:
                grouped[label_to_key[category_value]].append(row)

        return grouped

    def _row_for_tabular_export(self, record, category_key=None):
        """Map one internal record to display-header row for CSV/XLSX export."""
        row = {
            EXPORT_HEADERS["employee_name"]: record.get("employee_name", ""),
            EXPORT_HEADERS["account_name"]: record.get("account_name", ""),
            EXPORT_HEADERS["username"]: record.get("username", ""),
            EXPORT_HEADERS["account_password"]: record.get("account_password", ""),
            EXPORT_HEADERS["notes"]: record.get("notes", ""),
        }
        if category_key:
            row[EXPORT_HEADERS["category"]] = CATEGORY_LABELS[category_key]
        return row

    def _write_tabular_file(self, file_path, rows, include_category):
        """Write rows to CSV or XLSX using required headers."""
        ext = self._file_extension(file_path)
        headers = [
            EXPORT_HEADERS["employee_name"],
            EXPORT_HEADERS["account_name"],
            EXPORT_HEADERS["username"],
            EXPORT_HEADERS["account_password"],
            EXPORT_HEADERS["notes"],
        ]
        if include_category:
            headers.insert(0, EXPORT_HEADERS["category"])

        if ext == ".csv":
            with open(file_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    writer.writerow({header: row.get(header, "") for header in headers})
            return

        if ext == ".xlsx":
            if Workbook is None:
                raise RuntimeError("openpyxl is required for .xlsx export. Install openpyxl and try again.")
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Passwords"
            sheet.append(headers)
            for row in rows:
                sheet.append([row.get(header, "") for header in headers])
            workbook.save(file_path)
            return

        raise ValueError("Unsupported export format. Use .json, .csv, or .xlsx")

    def _read_tabular_file(self, file_path):
        """Read CSV or XLSX rows as dictionaries keyed by file headers."""
        ext = self._file_extension(file_path)

        if ext == ".csv":
            with open(file_path, "r", newline="", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)
                return [dict(row) for row in reader]

        if ext == ".xlsx":
            if load_workbook is None:
                raise RuntimeError("openpyxl is required for .xlsx import. Install openpyxl and try again.")
            workbook = load_workbook(file_path)
            sheet = workbook.active
            values = list(sheet.values)
            if not values:
                return []
            headers = [str(cell).strip() if cell is not None else "" for cell in values[0]]
            rows = []
            for raw_row in values[1:]:
                row_dict = {}
                for index, header in enumerate(headers):
                    if not header:
                        continue
                    cell_value = raw_row[index] if index < len(raw_row) else ""
                    row_dict[header] = "" if cell_value is None else str(cell_value)
                rows.append(row_dict)
            return rows

        raise ValueError("Unsupported import format. Use .json, .csv, or .xlsx")

    def _serialize_record(self, row):
        """Convert row values to JSON-safe structures, including datetime conversion."""
        output = dict(row)
        for key in ("created_at", "updated_at"):
            value = output.get(key)
            if isinstance(value, datetime):
                output[key] = value.isoformat(timespec="seconds")
        return output

    def _parse_record_datetime(self, primary_value, fallback_value):
        """Parse datetime values from DB/Python/ISO-string sources."""
        value = primary_value if primary_value not in (None, "") else fallback_value
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value

        value_text = str(value).strip()
        try:
            return datetime.fromisoformat(value_text)
        except ValueError:
            try:
                return datetime.strptime(value_text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

    def _file_extension(self, file_path):
        """Return lowercase file extension for import/export routing."""
        return os.path.splitext(file_path)[1].lower()


def main():
    """Unlock the local vault, then launch the password manager desktop application."""
    root = tk.Tk()
    root.withdraw()
    vault_path = os.path.join(BASE_DIR, "json_files", "password_data.vault")
    if os.path.exists(vault_path):
        master_password = simpledialog.askstring(
            "Unlock Vault", "Enter your master password:", show="*", parent=root
        )
        if master_password is None:
            root.destroy()
            return
    else:
        master_password = simpledialog.askstring(
            "Create Master Password",
            "Create a master password (12+ characters). It cannot be recovered:",
            show="*",
            parent=root,
        )
        confirmation = simpledialog.askstring(
            "Confirm Master Password", "Enter it again:", show="*", parent=root
        ) if master_password is not None else None
        if master_password != confirmation:
            messagebox.showerror("Password Mismatch", "The master passwords did not match.", parent=root)
            root.destroy()
            return
    try:
        app = PasswordManagerApp(root, master_password)
    except VaultCryptoError as exc:
        messagebox.showerror("Vault Locked", str(exc), parent=root)
        root.destroy()
        return
    _ = app
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
