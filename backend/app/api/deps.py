"""FastAPI security and authorization dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import TokenValidationError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Validate Bearer JWT token and return the active authenticated User."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing authentication token")

    try:
        payload = decode_access_token(credentials.credentials, settings)
        user_id = uuid.UUID(str(payload["sub"]))
    except (TokenValidationError, ValueError) as exc:
        raise _unauthorized("Invalid or expired authentication token") from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Inactive or unknown user")

    return user


def get_current_active_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the authenticated user has the 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
