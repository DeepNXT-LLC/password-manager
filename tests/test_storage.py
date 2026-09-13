from password_manager import CATEGORY_LABELS, StorageManager


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
        "account_password": "real-secret-for-test-only",
        "notes": "test",
    }
    manager.add_record("password_book", record)
    records = manager.fetch_records("password_book")
    assert len(records) == 1
    assert records[0]["account_password"] == record["account_password"]
    assert manager.fetch_record("password_book", records[0]["password_id"])["account_name"] == "Example"
    assert record["account_password"].encode() not in open(manager.vault_path, "rb").read()


def test_storage_rejects_legacy_plaintext_file(tmp_path, monkeypatch):
    monkeypatch.setattr("password_manager.BASE_DIR", str(tmp_path))
    legacy = tmp_path / "json_files" / "password_data.json"
    legacy.parent.mkdir()
    legacy.write_text(json_text := '{"password_book": []}', encoding="utf-8")

    import pytest
    from vault_crypto import VaultCryptoError

    with pytest.raises(VaultCryptoError):
        StorageManager("correct horse battery staple")
