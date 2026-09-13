import pytest

import password_manager as pm
from vault_crypto import (
    VaultCryptoError,
    decrypt_payload,
    encrypt_payload,
    load_encrypted_file,
    save_encrypted_file,
)


MASTER = "synthetic-master-password-123"


def make_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "BASE_DIR", str(tmp_path))
    return pm.StorageManager(MASTER)


def make_row(employee, account, username, password, category=None, password_id=None):
    row = {
        "Employee Name": employee,
        "Account Name": account,
        "Username": username,
        "Password": password,
        "Notes": "synthetic note",
        "Created At": "2026-01-01T00:00:00",
        "Updated At": "2026-01-01T00:00:00",
    }
    if category is not None:
        row["Category"] = category
    if password_id is not None:
        row["Password ID"] = password_id
    return row


def test_single_category_import_rejects_mislabeled_rows(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "mixed.vault"
    save_encrypted_file(
        str(backup),
        {"records": [make_row("Admin User", "Admin", "admin", "synthetic-admin", "Admin")]},
        MASTER,
    )

    imported, skipped = manager.import_records_from_file("mobile_devices", str(backup))

    assert (imported, skipped) == (0, 1)
    assert manager.fetch_records("mobile_devices") == []


def test_full_flat_backup_routes_rows_by_category(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "flat-full.vault"
    save_encrypted_file(
        str(backup),
        {
            "records": [
                make_row("Admin User", "Admin", "admin", "synthetic-admin", "Admin"),
                make_row("Phone User", "Phone", "phone", "synthetic-phone", "Mobile Devices"),
            ]
        },
        MASTER,
    )

    summary = manager.import_all_records_from_file(str(backup))

    assert summary["admin"] == 1
    assert summary["mobile_devices"] == 1
    assert len(manager.fetch_records("admin")) == 1
    assert len(manager.fetch_records("mobile_devices")) == 1


def test_full_import_rejects_rows_without_a_category_before_writing(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "uncategorized.vault"
    save_encrypted_file(
        str(backup),
        {"records": [make_row("Unknown User", "Unknown", "unknown", "synthetic-unknown")]},
        MASTER,
    )

    with pytest.raises(ValueError, match="valid Category"):
        manager.import_all_records_from_file(str(backup))

    assert all(manager.fetch_records(category) == [] for category in pm.CATEGORY_LABELS)


def test_full_import_rejects_malformed_category_container_before_writing(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "malformed-container.vault"
    save_encrypted_file(
        str(backup),
        {"password_book": "not-a-list", "mobile_devices": [], "computers": [], "admin": []},
        MASTER,
    )

    with pytest.raises(ValueError, match="category values must be lists"):
        manager.import_all_records_from_file(str(backup))

    assert all(manager.fetch_records(category) == [] for category in pm.CATEGORY_LABELS)


def test_duplicate_ids_fail_closed(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    payload = {
        "password_book": [
            {"password_id": 1, "employee_name": "A", "account_name": "A", "username": "a", "account_password": "one"},
            {"password_id": 1, "employee_name": "B", "account_name": "B", "username": "b", "account_password": "two"},
        ],
        "mobile_devices": [],
        "computers": [],
        "admin": [],
        "next_id": 2,
    }
    save_encrypted_file(manager.vault_path, payload, MASTER)

    with pytest.raises(VaultCryptoError, match="duplicate record IDs"):
        manager.fetch_records("password_book")


def test_duplicate_ids_in_import_fail_before_writing(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "duplicate-import.vault"
    save_encrypted_file(
        str(backup),
        {
            "records": [
                make_row("A", "One", "a", "synthetic-one", "Admin", 77),
                make_row("B", "Two", "b", "synthetic-two", "Mobile Devices", 77),
            ]
        },
        MASTER,
    )

    with pytest.raises(VaultCryptoError, match="duplicate record IDs"):
        manager.import_all_records_from_file(str(backup))

    assert all(manager.fetch_records(category) == [] for category in pm.CATEGORY_LABELS)


@pytest.mark.parametrize("bad_id", [0, -1, True, 1.5, "1.0", "1"])
def test_non_positive_or_boolean_stored_ids_fail_closed(tmp_path, monkeypatch, bad_id):
    manager = make_manager(tmp_path, monkeypatch)
    payload = {
        "password_book": [
            {
                "password_id": bad_id,
                "employee_name": "A",
                "account_name": "A",
                "username": "a",
                "account_password": "synthetic",
            }
        ],
        "mobile_devices": [],
        "computers": [],
        "admin": [],
        "next_id": 2,
    }
    save_encrypted_file(manager.vault_path, payload, MASTER)

    with pytest.raises(VaultCryptoError, match="invalid record ID"):
        manager.fetch_records("password_book")


def test_malformed_outer_vault_is_a_controlled_error(tmp_path):
    broken = tmp_path / "truncated.vault"
    broken.write_text('{"version": 1, "ciphertext":', encoding="utf-8")

    with pytest.raises(VaultCryptoError, match="read the vault file"):
        load_encrypted_file(str(broken), MASTER)


def test_full_import_rejects_malformed_required_row_before_writing(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "partly-bad.vault"
    save_encrypted_file(
        str(backup),
        {
            "records": [
                make_row("Good", "Account", "good", "synthetic-good", "Admin"),
                make_row("Bad", "Account", "bad", None, "Mobile Devices"),
            ]
        },
        MASTER,
    )

    with pytest.raises(ValueError, match="Employee Name.*Password"):
        manager.import_all_records_from_file(str(backup))

    assert all(manager.fetch_records(category) == [] for category in pm.CATEGORY_LABELS)


def test_full_import_is_atomic_if_final_save_fails(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    manager.add_record(
        "admin",
        {
            "employee_name": "Existing",
            "account_name": "Account",
            "username": "existing",
            "account_password": "synthetic-existing",
            "notes": "",
        },
    )
    before = manager.fetch_records("admin")

    backup = tmp_path / "atomic.vault"
    save_encrypted_file(
        str(backup),
        {
            "records": [
                make_row("New One", "Account", "new-one", "synthetic-one", "Admin"),
                make_row("New Two", "Account", "new-two", "synthetic-two", "Admin"),
            ]
        },
        MASTER,
    )

    def fail_save(_payload):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(manager, "_save_json", fail_save)
    with pytest.raises(OSError, match="synthetic disk failure"):
        manager.import_all_records_from_file(str(backup))

    monkeypatch.undo()
    assert manager.fetch_records("admin") == before


def test_missing_selected_record_clears_password_field(tmp_path, monkeypatch):
    class FakeVar:
        def __init__(self, value="stale"):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class FakeEntry:
        def configure(self, **kwargs):
            self.show = kwargs["show"]

    class FakeTree:
        def __init__(self):
            self.selected = ("99",)

        def selection(self):
            return self.selected

        def selection_remove(self, _selection):
            self.selected = ()

        def item(self, _selected_id, _option):
            return ("Employee", "Account", "user", "••••••••", "")

    manager = make_manager(tmp_path, monkeypatch)
    manager.fetch_record = lambda _category, _password_id: None
    app = object.__new__(pm.PasswordManagerApp)
    app.storage = manager
    app.tabs = {
        "password_book": {
            "employee_var": FakeVar(),
            "account_var": FakeVar(),
            "username_var": FakeVar(),
            "password_var": FakeVar("old-secret"),
            "notes_var": FakeVar(),
            "show_password_var": FakeVar(True),
            "password_entry": FakeEntry(),
            "tree": FakeTree(),
            "selected_id": "99",
        }
    }

    app.on_tree_select("password_book")

    assert app.tabs["password_book"]["selected_id"] is None
    assert app.tabs["password_book"]["password_var"].get() == ""
    assert app.tabs["password_book"]["password_entry"].show == "•"


def test_empty_selection_clears_password_field(tmp_path, monkeypatch):
    class FakeVar:
        def __init__(self, value="old"):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class FakeEntry:
        def configure(self, **kwargs):
            self.show = kwargs["show"]

    class FakeTree:
        def selection(self):
            return ()

        def selection_remove(self, _selection):
            pass

    manager = make_manager(tmp_path, monkeypatch)
    app = object.__new__(pm.PasswordManagerApp)
    app.tabs = {
        "password_book": {
            "employee_var": FakeVar(),
            "account_var": FakeVar(),
            "username_var": FakeVar(),
            "password_var": FakeVar("old-secret"),
            "notes_var": FakeVar(),
            "show_password_var": FakeVar(True),
            "password_entry": FakeEntry(),
            "tree": FakeTree(),
            "selected_id": "old-id",
        }
    }

    app.on_tree_select("password_book")

    assert app.tabs["password_book"]["selected_id"] is None
    assert app.tabs["password_book"]["password_var"].get() == ""
    assert app.tabs["password_book"]["password_entry"].show == "•"


def test_category_keyed_full_import_rejects_cross_category_duplicate_ids(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "duplicate-category-ids.vault"
    save_encrypted_file(
        str(backup),
        {
            "admin": [make_row("Admin", "Account", "admin", "synthetic-admin", password_id=77)],
            "mobile_devices": [make_row("Phone", "Account", "phone", "synthetic-phone", password_id=77)],
        },
        MASTER,
    )

    with pytest.raises(VaultCryptoError, match="duplicate record IDs"):
        manager.import_all_records_from_file(str(backup))


def test_category_keyed_full_import_rejects_conflicting_row_category(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    backup = tmp_path / "conflicting-category.vault"
    save_encrypted_file(
        str(backup),
        {
            "admin": [make_row("Admin", "Account", "admin", "synthetic-admin", "Mobile Devices")],
        },
        MASTER,
    )

    with pytest.raises(ValueError, match="does not match"):
        manager.import_all_records_from_file(str(backup))


@pytest.mark.parametrize("field,bad_value", [("kdf_n", 1), ("kdf_r", 1), ("kdf_p", 2)])
def test_tampered_kdf_metadata_is_rejected(field, bad_value):
    envelope = encrypt_payload({"secret": "synthetic-secret"}, MASTER)
    envelope[field] = bad_value

    with pytest.raises(VaultCryptoError):
        decrypt_payload(envelope, MASTER)


def test_none_required_import_values_are_rejected(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)

    assert manager._normalize_import_row(
        {
            "Employee Name": None,
            "Account Name": None,
            "Username": None,
            "Password": None,
            "Notes": None,
        }
    ) is None


def test_reload_clears_stale_selection_and_remasks(tmp_path, monkeypatch):
    class FakeVar:
        def __init__(self):
            self.value = "stale"

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    class FakeEntry:
        def configure(self, **kwargs):
            self.show = kwargs["show"]

    class FakeTree:
        def __init__(self):
            self.children = ["stale"]
            self.selected = ("stale",)

        def selection(self):
            return self.selected

        def selection_remove(self, _selection):
            self.selected = ()

        def get_children(self):
            return tuple(self.children)

        def delete(self, item_id):
            self.children.remove(item_id)

        def insert(self, _parent, _where, iid, values):
            self.children.append(iid)

    manager = make_manager(tmp_path, monkeypatch)
    manager.add_record(
        "password_book",
        {
            "employee_name": "User",
            "account_name": "Account",
            "username": "user",
            "account_password": "synthetic-password",
            "notes": "",
        },
    )
    app = object.__new__(pm.PasswordManagerApp)
    app.storage = manager
    app.tabs = {
        "password_book": {
            "employee_var": FakeVar(),
            "account_var": FakeVar(),
            "username_var": FakeVar(),
            "password_var": FakeVar(),
            "notes_var": FakeVar(),
            "show_password_var": FakeVar(),
            "password_entry": FakeEntry(),
            "tree": FakeTree(),
            "selected_id": "stale",
        }
    }

    app.load_tab_data("password_book")

    assert app.tabs["password_book"]["selected_id"] is None
    assert app.tabs["password_book"]["password_var"].get() == ""
    assert app.tabs["password_book"]["password_entry"].show == "•"
