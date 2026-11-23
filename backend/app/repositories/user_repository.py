"""Repository for User persistence and lookup queries."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Data access layer for User accounts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalize email address for case-insensitive uniqueness and lookup."""
        return email.strip().lower()

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by primary key UUID."""
        return self.db.scalar(select(User).where(User.id == user_id))

    def get_by_email(self, email: str) -> User | None:
        """Fetch a user by normalized email address."""
        normalized = self.normalize_email(email)
        return self.db.scalar(select(User).where(User.email == normalized))

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        role: str = "member",
    ) -> User:
        """Add and flush a new User record without committing the transaction."""
        user = User(
            email=self.normalize_email(email),
            password_hash=password_hash,
            full_name=full_name.strip() if full_name else None,
            role=role,
        )
        self.db.add(user)
        self.db.flush()
        return user
