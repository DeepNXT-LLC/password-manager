import json

import pytest

from vault_crypto import VaultCryptoError, decrypt_payload, encrypt_payload, load_encrypted_file, save_encrypted_file


def test_round_trip_and_wrong_password_fails():
    payload = {"password_book": [{"account_password": "do-not-leak"}]}
    envelope = encrypt_payload(payload, "correct horse battery staple")

    assert decrypt_payload(envelope, "correct horse battery staple") == payload
    with pytest.raises(VaultCryptoError):
        decrypt_payload(envelope, "wrong password entirely")


def test_tampering_fails_closed():
    envelope = encrypt_payload({"secret": "value"}, "correct horse battery staple")
    envelope["ciphertext"] = "A" + envelope["ciphertext"][1:]

    with pytest.raises(VaultCryptoError):
        decrypt_payload(envelope, "correct horse battery staple")


def test_file_round_trip_is_encrypted_and_atomic(tmp_path):
    path = tmp_path / "vault" / "password_data.vault"
    secret = "do-not-leak-this-password"
    save_encrypted_file(str(path), {"secret": secret}, "correct horse battery staple")

    assert load_encrypted_file(str(path), "correct horse battery staple") == {"secret": secret}
    assert secret.encode("utf-8") not in path.read_bytes()
    assert not list(path.parent.glob(".vault-*.tmp"))


def test_invalid_master_password_is_rejected():
    with pytest.raises(VaultCryptoError):
        encrypt_payload({}, "too-short")
