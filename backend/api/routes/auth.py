"""Authentication routes: login and registration.

Issues HS256 JWTs whose ``sub`` claim is the user id, compatible with
``api.middleware.auth.get_current_user_id``. Passwords are hashed with bcrypt
via passlib.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_session
from models.tables import User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "employee"  # "employee" | "admin"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


def _create_token(user_id: str, email: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    return jwt.encode(
        {"sub": user_id, "email": email, "role": role, "exp": expire},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_session)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return TokenResponse(
        access_token=_create_token(str(user.id), user.email, user.role),
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest, db: AsyncSession = Depends(get_session)
) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    if body.role not in {"employee", "admin"}:
        raise HTTPException(status_code=422, detail="role must be employee or admin")
    user = User(
        email=body.email,
        hashed_password=pwd_context.hash(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(
        access_token=_create_token(str(user.id), user.email, user.role),
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )
