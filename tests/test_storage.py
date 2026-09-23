import os

import pytest

from password_manager import CATEGORY_LABELS, StorageManager
from vault_crypto import VaultCryptoError, save_encrypted_file


def test_storage_creates_encrypted_vault_and_crud(tmp_path, monkeypatch):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("password_manager.LOG_DIR", str(tmp_path / "logs"))
    manager = StorageManager("correct horse battery staple")

    assert manager.vault_path.endswith("password_data.vault")
    assert manager.fetch_records("password_book") == []

    record = {
        "employee_name": "Owner",
        "account_name": "Example",
        "username": "owner@example.com",
        "phone_number": "",
        "website_url": "https://example.com",
        "account_password": "real-secret-for-test-only",
        "notes": "test",
    }
    manager.add_record("password_book", record)
    records = manager.fetch_records("password_book")
    assert len(records) == 1
    assert records[0]["website_url"] == "https://example.com"
    assert records[0]["account_password"] == record["account_password"]
    assert manager.fetch_record("password_book", records[0]["password_id"])["account_name"] == "Example"
    assert record["account_password"].encode() not in open(manager.vault_path, "rb").read()


def test_mobile_device_phone_number_is_stored(tmp_path, monkeypatch):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    manager = StorageManager("correct horse battery staple")

    manager.add_record(
        "mobile_devices",
        {
            "employee_name": "Owner",
            "account_name": "Phone",
            "username": "owner-phone",
            "phone_number": "+1-555-0100",
            "website_url": "https://carrier.example",
            "account_password": "mobile-secret",
            "notes": "primary device",
        },
    )

    records = manager.fetch_records("mobile_devices")
    assert len(records) == 1
    assert records[0]["phone_number"] == "+1-555-0100"
    assert records[0]["website_url"] == "https://carrier.example"


def test_storage_rejects_legacy_plaintext_file(tmp_path, monkeypatch):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    legacy = tmp_path / "json_files" / "password_data.json"
    legacy.parent.mkdir()
    legacy.write_text(json_text := '{"password_book": []}', encoding="utf-8")

    with pytest.raises(VaultCryptoError):
        StorageManager("correct horse battery staple")


def test_malformed_encrypted_backup_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    manager = StorageManager("correct horse battery staple")
    backup = tmp_path / "malformed.vault"
    save_encrypted_file(str(backup), {"unexpected": "shape"}, "correct horse battery staple")

    with pytest.raises(ValueError, match="recognized password categories"):
        manager.import_all_records_from_file(str(backup))


@pytest.mark.parametrize("full_backup", [False, True])
@pytest.mark.parametrize("alias", ["direct", "relative", "symlink", "hardlink"])
def test_export_rejects_live_vault_destination_without_changing_it(
    tmp_path, monkeypatch, full_backup, alias
):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    manager = StorageManager("correct horse battery staple")
    manager.add_record("password_book", {
        "employee_name": "Synthetic", "account_name": "Example", "username": "user",
        "account_password": " synthetic-only ", "notes": "",
    })
    before = (tmp_path / "json_files" / "password_data.vault").read_bytes()
    destination = manager.vault_path
    if alias == "relative":
        destination = os.path.join(tmp_path, "json_files", "..", "json_files", "password_data.vault")
    elif alias in ("symlink", "hardlink"):
        destination = str(tmp_path / f"{alias}.vault")
        try:
            if alias == "symlink":
                os.symlink(manager.vault_path, destination)
            else:
                os.link(manager.vault_path, destination)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"{alias} unavailable: {exc}")

    with pytest.raises(ValueError, match="active vault"):
        if full_backup:
            manager.export_all_records_to_file(destination)
        else:
            manager.export_records_to_file("password_book", destination)

    assert (tmp_path / "json_files" / "password_data.vault").read_bytes() == before
    assert len(manager.fetch_records("password_book")) == 1


@pytest.mark.parametrize("full_backup", [False, True])
def test_export_refuses_to_replace_existing_backup(tmp_path, monkeypatch, full_backup):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    manager = StorageManager("correct horse battery staple")
    backup = tmp_path / "backup.vault"
    if full_backup:
        manager.export_all_records_to_file(str(backup))
    else:
        manager.export_records_to_file("password_book", str(backup))
    original = backup.read_bytes()

    with pytest.raises(FileExistsError):
        if full_backup:
            manager.export_all_records_to_file(str(backup))
        else:
            manager.export_records_to_file("password_book", str(backup))
    assert backup.read_bytes() == original


@pytest.mark.parametrize("full_backup", [False, True])
def test_export_does_not_overwrite_vault_after_guard_alias_swap(tmp_path, monkeypatch, full_backup):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    manager = StorageManager("correct horse battery staple")
    vault = tmp_path / "json_files" / "password_data.vault"
    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    alias = tmp_path / "export-alias"
    try:
        alias.symlink_to(safe_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    destination = alias / "password_data.vault"
    before = vault.read_bytes()
    actual_save = __import__("password_manager").save_encrypted_file

    def swap_then_save(*args, **kwargs):
        alias.unlink()
        alias.symlink_to(vault.parent, target_is_directory=True)
        return actual_save(*args, **kwargs)

    monkeypatch.setattr("password_manager.save_encrypted_file", swap_then_save)
    with pytest.raises(FileExistsError):
        if full_backup:
            manager.export_all_records_to_file(str(destination))
        else:
            manager.export_records_to_file("password_book", str(destination))
    assert vault.read_bytes() == before
