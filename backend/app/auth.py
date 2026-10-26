from fastapi import Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
import hashlib
import logging

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.services.security import (
    create_session_token,
    verify_session_token_claims,
    create_csrf_token,
    verify_csrf_token,
)

logger = logging.getLogger("csv_analyzer.auth")

STATE_CHANGING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def set_auth_cookies(response: Response, db: Session, user_id: int) -> None:
    """Stage a server-side session before issuing its authentication cookies."""
    session_id = uuid4().hex
    token = create_session_token(user_id, session_id)
    now = datetime.now(timezone.utc)
    db.add(UserSession(
        user_id=user_id,
        session_id=session_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        is_revoked=False,
        expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    ))
    db.flush()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    set_csrf_cookie(response, create_csrf_token(user_id))

def clear_auth_cookies(response: Response):
    """Invalidates and removes authentication and CSRF cookies."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
    )


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Primary authentication dependency for protected endpoints.
    
    1. Extracts session from HttpOnly cookie (or Bearer token for programmatic API clients).
    2. Validates session signature and expiration.
    3. Enforces CSRF token verification on state-changing requests when authenticated via cookies.
    4. Retrieves and returns active User entity.
    """
    token: Optional[str] = None
    is_cookie_auth = False

    # 1. Check HttpOnly session cookie
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        token = cookie_token
        is_cookie_auth = True
    else:
        # Check Authorization Bearer header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to access this resource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Verify token signature and timestamp
    claims = verify_session_token_claims(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        active_session = (
            db.query(UserSession)
            .filter(
                UserSession.session_id == claims["session_id"],
                UserSession.token_hash == token_hash,
                UserSession.user_id == claims["user_id"],
            )
            .first()
        )
        if not active_session or active_session.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked or is no longer active.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        expires_at = active_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has expired or is invalid. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = db.query(User).filter(User.id == claims["user_id"]).first()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("Database error while validating an authentication session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication could not be verified. Please try again later.",
        ) from exc

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been deactivated.",
        )
    request.state.active_session = active_session

    # 4. CSRF Protection for state-changing cookie requests
    if is_cookie_auth and request.method in STATE_CHANGING_METHODS:
        # Public login and registration do not have an authenticated CSRF token yet.
        if request.url.path not in ("/api/auth/login", "/api/auth/register"):
            csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
            csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)

            if not csrf_header or not csrf_cookie:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF verification failed: missing X-CSRF-Token header or CSRF cookie.",
                )

            if csrf_header != csrf_cookie:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF verification failed: token mismatch between header and cookie.",
                )

            csrf_user_id = verify_csrf_token(csrf_header)
            if not csrf_user_id or csrf_user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF verification failed: invalid or expired CSRF token.",
                )

    return user
