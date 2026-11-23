"""Password hashing, JWT access token management, and Fernet OAuth token encryption."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenValidationError(Exception):
    """Raised when a JWT access token is expired, malformed, or invalid."""


class TokenEncryptionConfigError(Exception):
    """Raised when the configured Fernet encryption key is invalid."""


class TokenDecryptionError(Exception):
    """Raised when encrypted token ciphertext is invalid or uses a mismatched key."""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(
    subject: str | uuid.UUID,
    settings: Settings,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Create a signed JWT access token and return (token, expires_in_seconds)."""
    delta = expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    now = datetime.now(UTC)
    expire_at = now + delta

    payload: dict[str, Any] = {}
    if extra_claims:
        payload.update(extra_claims)
    payload.update(
        {
            "sub": str(subject),
            "type": "access",
            "iat": now,
            "exp": expire_at,
        }
    )

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, max(0, int(delta.total_seconds()))


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a signed JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenValidationError("Invalid or expired access token") from exc

    if payload.get("type") != "access" or not payload.get("sub"):
        raise TokenValidationError("Invalid access token claims")
    return payload


class TokenEncryptor:
    """Symmetric Fernet encryptor/decryptor for persisted OAuth tokens."""

    def __init__(self, key: str | bytes) -> None:
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        try:
            self._fernet = Fernet(key_bytes)
        except (ValueError, TypeError) as exc:
            raise TokenEncryptionConfigError(
                "OAUTH_TOKEN_ENCRYPTION_KEY must be a valid 32-byte url-safe base64 Fernet key"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext OAuth token into a UTF-8 Fernet token string."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a stored Fernet ciphertext back into the plaintext OAuth token."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise TokenDecryptionError("Failed to decrypt OAuth token") from exc


def encrypt_oauth_token(plaintext: str, settings: Settings) -> str:
    """Encrypt an OAuth token using the application's configured Fernet key."""
    encryptor = TokenEncryptor(settings.OAUTH_TOKEN_ENCRYPTION_KEY.get_secret_value())
    return encryptor.encrypt(plaintext)


def decrypt_oauth_token(ciphertext: str, settings: Settings) -> str:
    """Decrypt an OAuth token using the application's configured Fernet key."""
    encryptor = TokenEncryptor(settings.OAUTH_TOKEN_ENCRYPTION_KEY.get_secret_value())
    return encryptor.decrypt(ciphertext)
