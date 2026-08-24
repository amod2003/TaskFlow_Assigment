from collections.abc import AsyncGenerator

import fakeredis.aioredis as fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.core.database import Base
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

# In-memory async SQLite engine for ultra-fast, isolated testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a test database session."""
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> AsyncGenerator[fakeredis.FakeRedis, None]:
    """Yields an in-memory isolated FakeRedis instance."""
    redis_instance = fakeredis.FakeRedis(decode_responses=True)
    yield redis_instance
    await redis_instance.aclose()


@pytest_asyncio.fixture(scope="function")
async def client(
    db_session: AsyncSession, fake_redis: fakeredis.FakeRedis
) -> AsyncGenerator[AsyncClient, None]:
    """Provides an AsyncClient connected to the FastAPI app with test db and redis overrides."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_redis() -> AsyncGenerator[fakeredis.FakeRedis, None]:
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Creates primary test user."""
    user = User(
        email="alice@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Alice Wonderland",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_user_2(db_session: AsyncSession) -> User:
    """Creates secondary test user for authorization boundary testing."""
    user = User(
        email="bob@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Bob Builder",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user: User) -> dict[str, str]:
    """Generates valid JWT Authorization headers for test_user (Alice)."""
    token = create_access_token(subject=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def auth_headers_2(test_user_2: User) -> dict[str, str]:
    """Generates valid JWT Authorization headers for test_user_2 (Bob)."""
    token = create_access_token(subject=test_user_2.id)
    return {"Authorization": f"Bearer {token}"}
