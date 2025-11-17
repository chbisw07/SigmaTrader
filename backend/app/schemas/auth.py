from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, constr


class UserRead(BaseModel):
    id: int
    username: str
    role: str
    display_name: Optional[str] = None
    theme_id: Optional[str] = None

    class Config:
        orm_mode = True


class RegisterRequest(BaseModel):
    username: constr(min_length=3, max_length=64)  # type: ignore[type-arg]
    password: constr(min_length=6, max_length=128)  # type: ignore[type-arg]
    display_name: Optional[constr(max_length=128)] = None  # type: ignore[type-arg]


class LoginRequest(BaseModel):
    username: constr(min_length=1, max_length=64)  # type: ignore[type-arg]
    password: constr(min_length=1, max_length=128)  # type: ignore[type-arg]


class ChangePasswordRequest(BaseModel):
    current_password: constr(min_length=1, max_length=128)  # type: ignore[type-arg]
    new_password: constr(min_length=6, max_length=128)  # type: ignore[type-arg]


class ThemeUpdateRequest(BaseModel):
    theme_id: constr(min_length=1, max_length=32)  # type: ignore[type-arg]


__all__ = [
    "UserRead",
    "RegisterRequest",
    "LoginRequest",
    "ChangePasswordRequest",
    "ThemeUpdateRequest",
]
