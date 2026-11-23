"""Unit tests for password hashing, JWT tokens, and Fernet OAuth token encryption."""

import uuid
from datetime import timedelta

import jwt
import pytest
from app.config import Settings, get_settings
from app.utils.security import (
    TokenDecryptionError,
    TokenEncryptionConfigError,
    TokenEncryptor,
    TokenValidationError,
    create_access_token,
    decode_access_token,
    decrypt_oauth_token,
    encrypt_oauth_token,
    hash_password,
    verify_password,
)
from cryptography.fernet import Fernet


def test_hash_and_verify_password() -> None:
    password = "StrongSeoPassword!2026"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != password
    assert hash1 != hash2
    assert verify_password(password, hash1) is True
    assert verify_password("WrongPassword", hash1) is False


def test_create_and_decode_access_token() -> None:
    settings = get_settings()
    user_id = uuid.uuid4()

    token, expires_in = create_access_token(user_id, settings)
    assert expires_in == settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    payload = decode_access_token(token, settings)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_expired_token_raises() -> None:
    settings = get_settings()
    token, _ = create_access_token(
        uuid.uuid4(),
        settings,
        expires_delta=timedelta(seconds=-5),
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(token, settings)


def test_decode_tampered_or_wrong_secret_token_raises() -> None:
    settings = get_settings()
    token, _ = create_access_token(uuid.uuid4(), settings)
    tampered = token[:-4] + "abcd"
    with pytest.raises(TokenValidationError):
        decode_access_token(tampered, settings)

    other_settings = Settings(JWT_SECRET_KEY="different-secret-key-at-least-32-chars-long")
    with pytest.raises(TokenValidationError):
        decode_access_token(token, other_settings)


def test_decode_wrong_token_type_raises() -> None:
    settings = get_settings()
    bad_token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "iat": 1700000000,
            "exp": 9999999999,
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(bad_token, settings)


@pytest.mark.parametrize(
    "raw_token",
    [
        "ya29.a0AfH6SMBx_ascii_oauth_token_123456",
        "refresh-token-tiếng-việt-có-dấu-✓",
    ],
)
def test_oauth_token_encrypt_decrypt_roundtrip(raw_token: str) -> None:
    settings = get_settings()
    ciphertext = encrypt_oauth_token(raw_token, settings)
    assert ciphertext != raw_token
    assert decrypt_oauth_token(ciphertext, settings) == raw_token


def test_token_encryptor_error_handling() -> None:
    key1 = Fernet.generate_key().decode("utf-8")
    key2 = Fernet.generate_key().decode("utf-8")

    enc1 = TokenEncryptor(key1)
    enc2 = TokenEncryptor(key2)

    ciphertext = enc1.encrypt("secret-refresh-token")
    with pytest.raises(TokenDecryptionError):
        enc2.decrypt(ciphertext)

    with pytest.raises(TokenDecryptionError):
        enc1.decrypt("not-valid-fernet-ciphertext")

    with pytest.raises(TokenEncryptionConfigError):
        TokenEncryptor("invalid-short-key")
