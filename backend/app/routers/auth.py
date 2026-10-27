from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import logging
import secrets

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.auth import (
    get_current_user,
    set_auth_cookies,
    set_csrf_cookie,
    clear_auth_cookies,
)
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    AuthMessage,
    CsrfResponse,
)
from app.services.security import hash_password, verify_password, create_csrf_token

logger = logging.getLogger("csv_analyzer.auth_router")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Registers a new user account with unique username and email. Hashes password securely and sets initial session cookies."
)
def register_user(
    payload: UserRegister,
    response: Response,
    db: Session = Depends(get_db),
):
    """Register a new user account and automatically establish a session."""
    if settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration is disabled in demo mode.",
        )

    # 1. Enforce unique username
    existing_username = db.query(User).filter(User.username == payload.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username already exists."
        )

    # 2. Enforce unique email
    existing_email = db.query(User).filter(User.email == payload.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists."
        )

    # 3. Hash password and persist user
    hashed = hash_password(payload.password)
    new_user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hashed,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    # 4. Automatically establish session with HttpOnly and CSRF cookies
    set_auth_cookies(response, db, new_user.id)
    db.commit()
    db.refresh(new_user)
    logger.info("Registered new user id=%s.", new_user.id)

    return UserResponse.model_validate(new_user)


@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in user",
    description="Authenticates user by username or email and password. Sets secure HttpOnly session cookie and CSRF cookie."
)
def login_user(
    payload: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate user credentials and issue secure session cookies."""
    if settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Login is disabled in demo mode.",
        )

    identifier = payload.username_or_email.strip()

    # Find user by username or email
    try:
        user = (
            db.query(User)
            .filter(or_(User.username == identifier, User.email == identifier.lower()))
            .first()
        )
    except SQLAlchemyError as exc:
        logger.error("Database error during login.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable. Please try again later.",
        ) from exc

    # Constant-time verification to prevent user enumeration via timing
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact support."
        )

    # Set session and CSRF cookies
    try:
        set_auth_cookies(response, db, user.id)
        db.commit()
    except SQLAlchemyError as exc:
        try:
            db.rollback()
        except SQLAlchemyError:
            logger.error("Database rollback failed after a login error.")
        logger.error("Database error while creating a login session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable. Please try again later.",
        ) from exc
    logger.info("User logged in id=%s.", user.id)

    return UserResponse.model_validate(user)


@router.post(
    "/demo",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Start an isolated demo session",
)
def create_demo_session(
    response: Response,
    db: Session = Depends(get_db),
):
    """Create a dedicated, password-inaccessible account for one demo session."""
    if not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled.",
        )

    identity = secrets.token_hex(16)
    demo_user = User(
        username=f"demo_{identity}",
        email=f"demo-{identity}@example.com",
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        is_active=True,
    )
    try:
        db.add(demo_user)
        db.flush()
        set_auth_cookies(response, db, demo_user.id)
        db.commit()
        db.refresh(demo_user)
    except IntegrityError as exc:
        db.rollback()
        logger.error("Database uniqueness error while creating a demo session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A demo session could not be started. Please try again.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Database error while creating a demo session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A demo session could not be started. Please try again.",
        ) from exc

    return UserResponse.model_validate(demo_user)


@router.post(
    "/logout",
    response_model=AuthMessage,
    status_code=status.HTTP_200_OK,
    summary="Log out user",
    description="Clears and invalidates the session and CSRF cookies."
)
def logout_user(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke the active server-side session and clear authentication cookies."""
    request.state.active_session.is_revoked = True
    db.commit()
    clear_auth_cookies(response)
    logger.info("User logged out: id=%s", current_user.id)
    return AuthMessage(message="Logged out successfully.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user."
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Return the profile of the current authenticated user."""
    return UserResponse.model_validate(current_user)


@router.get(
    "/csrf",
    response_model=CsrfResponse,
    status_code=status.HTTP_200_OK,
    summary="Get or refresh CSRF token",
    description="Returns a valid CSRF token and sets the csrf_token cookie."
)
def get_csrf_token(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Generate and set a fresh CSRF token cookie for the authenticated session."""
    token = create_csrf_token(current_user.id)
    set_csrf_cookie(response, token)
    return CsrfResponse(csrf_token=token)
