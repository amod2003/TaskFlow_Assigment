from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserResponse


class AuthService:
    """Service handling user registration, authentication, and token management."""

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        """Fetch user by case-insensitive email."""
        result = await db.execute(select(User).where(User.email == email.lower().strip()))
        return result.scalars().first()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        """Fetch user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @classmethod
    async def register_user(cls, db: AsyncSession, user_in: UserCreate) -> User:
        """Registers a new user after validating email uniqueness."""
        existing_user = await cls.get_user_by_email(db, user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )

        hashed_pw = hash_password(user_in.password)
        db_user = User(
            email=user_in.email.lower().strip(),
            hashed_password=hashed_pw,
            full_name=user_in.full_name,
            is_active=True,
        )
        db.add(db_user)
        await db.flush()
        await db.refresh(db_user)
        return db_user

    @classmethod
    async def authenticate_user(cls, db: AsyncSession, login_data: LoginRequest) -> TokenResponse:
        """Authenticates user credentials and generates a JWT access token."""
        user = await cls.get_user_by_email(db, login_data.email)
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated.",
            )

        token = create_access_token(subject=user.id)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )
