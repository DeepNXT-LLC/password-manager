"""Authenticated encryption helpers for the local password vault."""

import base64
import json
import os
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


FORMAT_VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
AAD = b"password-manager-vault-v1"


class VaultCryptoError(ValueError):
    """Raised when a vault cannot be safely decrypted or validated."""


def _derive_key(master_password, salt):
    if not isinstance(master_password, str) or len(master_password) < 12:
        raise VaultCryptoError("Master password must contain at least 12 characters.")
    return Scrypt(
        salt=salt,
        length=KEY_BYTES,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    ).derive(master_password.encode("utf-8"))


def encrypt_payload(payload, master_password):
    """Return a JSON-safe authenticated-encryption envelope."""
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = _derive_key(master_password, salt)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, AAD)
    return {
        "version": FORMAT_VERSION,
        "kdf": "scrypt",
        "kdf_n": SCRYPT_N,
        "kdf_r": SCRYPT_R,
        "kdf_p": SCRYPT_P,
        "cipher": "AES-256-GCM",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_payload(envelope, master_password):
    """Decrypt and validate a vault envelope, failing closed on any error."""
    try:
        if not isinstance(envelope, dict) or envelope.get("version") != FORMAT_VERSION:
            raise VaultCryptoError("Unsupported vault format.")
        if envelope.get("kdf") != "scrypt" or envelope.get("cipher") != "AES-256-GCM":
            raise VaultCryptoError("Unsupported vault cryptography.")
        if (
            envelope.get("kdf_n") != SCRYPT_N
            or envelope.get("kdf_r") != SCRYPT_R
            or envelope.get("kdf_p") != SCRYPT_P
        ):
            raise VaultCryptoError("Unsupported vault KDF parameters.")
        salt = base64.b64decode(envelope["salt"], validate=True)
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES or len(ciphertext) < 16:
            raise VaultCryptoError("Invalid vault envelope.")
        key = _derive_key(master_password, salt)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise VaultCryptoError("Vault payload must be an object.")
        return payload
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidTag) as exc:
        raise VaultCryptoError("Unable to unlock vault. Check the master password or file integrity.") from exc


def save_encrypted_file(path, payload, master_password):
    """Write an encrypted vault atomically, creating its parent directory."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    envelope = encrypt_payload(payload, master_password)
    fd, temp_path = tempfile.mkstemp(prefix=".vault-", suffix=".tmp", dir=parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(envelope, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def load_encrypted_file(path, master_password):
    """Load and decrypt an encrypted vault file."""
    with open(path, "r", encoding="utf-8") as file:
        envelope = json.load(file)
    return decrypt_payload(envelope, master_password)
