from pathlib import Path

import secrets

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def generate_token(length, as_hex: bool = False):
    """
    Return a securely generated random token.
    The token will be `length` bytes long. If `as_hex` is True, it will be returned
    as a hexadecimal string, otherwise as a URL-safe base64-encoded string.
    """
    if as_hex:
        return secrets.token_hex(length)
    return secrets.token_urlsafe(length)


def hide_token(token, short: bool = True, chars: int = 3):
    """
    Returns hidden token, e.g. 1234567890 -> 123******890

    If short is True, returns a shorter version, e.g. 1234567890 -> 123***890
    """
    if short:
        return f"{token[:chars]}***{token[-chars:]}"
    return f"{token[:chars]}{'*' * (len(token)-chars*2)}{token[-chars:]}"


def generate_es256_pair() -> tuple[str, str]:
    """
    Generate an ES256 (ECDSA P-256) key pair for credential encryption.

    The private key should be stored securely and used by PERMYT to sign or
    encrypt credentials before persisting them. The public key can be shared
    with services to verify signatures or decrypt credentials.

    Returns:
        tuple[str, str]: A (private_key_pem, public_key_pem) tuple, both as
        PEM-encoded strings ready to be stored in the database.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def load_private_key(private_key: str):
    """
    Load private key from a PEM string or file path.

    Args:
        private_key (str): PEM string or path to PEM file.

    Returns:
        Private key object for signing operations.

    Raises:
        ValueError: If the key format is invalid or file does not exist.
    """
    if private_key.startswith("-----BEGIN"):
        pem = private_key
    else:
        path = Path(private_key)
        if not path.exists():
            raise ValueError(f"Private key file not found: {private_key}")
        with open(path, "r", encoding="utf-8") as f:
            pem = f.read()

    if not pem.startswith("-----BEGIN"):
        raise ValueError("Invalid private key format.")

    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
