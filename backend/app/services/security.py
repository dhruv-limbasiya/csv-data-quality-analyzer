import bcrypt
from typing import Any, Dict, Optional
from uuid import uuid4
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.config import settings
import logging

logger = logging.getLogger("csv_analyzer.security")

# Initialize serializers using app secrets
_session_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session-auth")
_csrf_serializer = URLSafeTimedSerializer(settings.CSRF_SECRET, salt="csrf-protection")


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt with a random salt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against the stored bcrypt hash using constant-time check."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        logger.warning("Password hash verification failed.")
        return False


def create_session_token(user_id: int, session_id: Optional[str] = None) -> str:
    """Generate a signed token with a unique identifier for an authenticated session."""
    return _session_serializer.dumps({
        "user_id": user_id,
        "session_id": session_id or uuid4().hex,
    })


def verify_session_token_claims(token: str) -> Optional[Dict[str, Any]]:
    """Validate a session token and return its user and session identifiers."""
    if not token:
        return None
    try:
        max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        data = _session_serializer.loads(token, max_age=max_age_seconds)
        user_id = data.get("user_id")
        session_id = data.get("session_id")
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or not isinstance(session_id, str)
            or not session_id
        ):
            return None
        return {"user_id": user_id, "session_id": session_id}
    except (SignatureExpired, BadSignature):
        logger.debug("Invalid or expired session token.")
        return None
    except Exception:
        logger.warning("Unexpected error validating session token.")
        return None


def verify_session_token(token: str) -> Optional[int]:
    """
    Validate session token signature and check expiration.
    Returns user_id if valid, or None if expired/tampered.
    """
    claims = verify_session_token_claims(token)
    return claims["user_id"] if claims else None


def create_csrf_token(user_id: int) -> str:
    """Generate a signed CSRF token tied to the user's session."""
    return _csrf_serializer.dumps({"user_id": user_id})


def verify_csrf_token(token: str) -> Optional[int]:
    """
    Validate CSRF token signature and expiration.
    Returns user_id if valid, or None if invalid.
    """
    if not token:
        return None
    try:
        max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        data = _csrf_serializer.loads(token, max_age=max_age_seconds)
        return data.get("user_id")
    except (SignatureExpired, BadSignature):
        return None
    except Exception:
        logger.warning("Unexpected error validating CSRF token.")
        return None
