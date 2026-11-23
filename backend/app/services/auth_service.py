"""Application authentication service for user registration and JWT issuance."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.utils.security import create_access_token, hash_password, verify_password


class EmailAlreadyRegisteredError(Exception):
    """Raised when attempting to register with an already-used email address."""


class InvalidCredentialsError(Exception):
    """Raised when login email or password is invalid."""


class InactiveUserError(Exception):
    """Raised when an inactive user attempts to authenticate."""


class AuthService:
    """Handles user registration, password verification, and JWT issuance."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.users = UserRepository(db)

    def register_user(self, payload: UserRegisterRequest) -> User:
        """Register a new active member account with a hashed password."""
        existing = self.users.get_by_email(payload.email)
        if existing is not None:
            raise EmailAlreadyRegisteredError("Email is already registered")

        password_hash = hash_password(payload.password)
        try:
            user = self.users.create(
                email=payload.email,
                password_hash=password_hash,
                full_name=payload.full_name,
                role="member",
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmailAlreadyRegisteredError("Email is already registered") from exc

        self.db.refresh(user)
        return user

    def authenticate_user(self, payload: UserLoginRequest) -> tuple[User, str, int]:
        """Validate credentials and issue a signed JWT access token."""
        user = self.users.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password")

        if not user.is_active:
            raise InactiveUserError("User account is inactive")

        token, expires_in = create_access_token(user.id, self.settings)
        return user, token, expires_in
