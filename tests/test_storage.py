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
