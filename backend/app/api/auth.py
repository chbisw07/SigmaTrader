from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.pydantic_compat import PYDANTIC_V2
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ThemeUpdateRequest,
    UserRead,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).one_or_none()


def _get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).one_or_none()


def _user_to_schema(user: User) -> UserRead:
    """Convert a User ORM object into its API schema."""

    if PYDANTIC_V2 and hasattr(UserRead, "model_validate"):
        return UserRead.model_validate(user)  # type: ignore[arg-type]
    return UserRead.from_orm(user)


def _set_session_cookie(
    request: Request,
    response: Response,
    token: str,
    settings: Settings,
) -> None:
    # Prefer proxy-provided scheme (common in prod behind a reverse proxy).
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme
    secure = scheme.lower() == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def _ensure_env_admin_user(
    db: Session,
    settings: Settings,
    *,
    username: str,
    password: str,
) -> User | None:
    """Allow logging in with ST_ADMIN_USERNAME/PASSWORD even if no DB user exists.

    SigmaTrader supports a legacy HTTP Basic admin mode (ST_ADMIN_*). The web UI
    uses the session-based auth APIs. To keep setup simple and avoid "can't
    login" surprises, we bootstrap (or update) a matching ADMIN user record on
    successful env-admin authentication.
    """

    admin_username = (settings.admin_username or "").strip()
    admin_password = settings.admin_password or ""
    if not admin_username:
        return None

    if username != admin_username:
        return None

    # Do not accept empty admin passwords.
    if not admin_password:
        return None

    if not secrets.compare_digest(password, admin_password):
        return None

    user = _get_user_by_username(db, admin_username)
    if user is None:
        user = User(
            username=admin_username,
            password_hash=hash_password(password),
            role="ADMIN",
            display_name="Administrator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # Keep role/password aligned with env-admin credentials.
    changed = False
    if user.role != "ADMIN":
        user.role = "ADMIN"
        changed = True
    if not verify_password(password, user.password_hash):
        user.password_hash = hash_password(password)
        changed = True
    if changed:
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    try:
        user_id, _payload = decode_session_token(settings, token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        ) from exc

    user = _get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found for this session.",
        )
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Return the current user or None if not authenticated.

    This is useful for admin guards that want to allow either a logged-in
    admin user or fall back to other mechanisms (e.g., HTTP Basic).
    """

    try:
        return get_current_user(request, db=db, settings=settings)
    except HTTPException:
        return None


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserRead:
    """Register a new user.

    For now registration is open; in future sprints this can be restricted
    to admins only if desired.
    """

    existing = _get_user_by_username(db, payload.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken.",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="TRADER",
        display_name=payload.display_name or payload.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserRead:
    """Authenticate a user and issue a session cookie."""

    user = _get_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        user = _ensure_env_admin_user(
            db,
            settings,
            username=payload.username,
            password=payload.password,
        )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_session_token(settings, user_id=user.id)
    _set_session_cookie(request, response, token, settings)

    return _user_to_schema(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def logout(response: Response) -> None:
    """Clear the current session cookie."""

    _clear_session_cookie(response)


@router.get("/me", response_model=UserRead)
def read_current_user(user: User = Depends(get_current_user)) -> UserRead:
    """Return the currently authenticated user."""

    return _user_to_schema(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Change the password for the currently authenticated user."""

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()


@router.post("/theme", response_model=UserRead)
def update_theme(
    payload: ThemeUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    """Update the preferred UI theme for the current user."""

    user.theme_id = payload.theme_id
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


__all__: list[str] = ["router", "get_current_user", "get_current_user_optional"]
