import pytest
from httpx import AsyncClient

from app.core.security import hash_password, verify_password
from app.models.user import User


@pytest.mark.asyncio
async def test_password_hashing() -> None:
    """Test Argon2 password hashing and constant-time verification."""
    raw_password = "SecurePassword123!"
    hashed = hash_password(raw_password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


@pytest.mark.asyncio
async def test_user_signup_success(client: AsyncClient) -> None:
    """Test successful user registration."""
    payload = {
        "email": "newuser@example.com",
        "password": "StrongPassword123!",
        "full_name": "New User",
    }
    response = await client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_user_signup_duplicate_email(client: AsyncClient, test_user: User) -> None:
    """Test rejection when registering with an existing email."""
    payload = {
        "email": test_user.email,
        "password": "AnotherPassword123!",
        "full_name": "Duplicate User",
    }
    response = await client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_user_signup_validation_errors(client: AsyncClient) -> None:
    """Test validation errors for malformed email and short passwords."""
    # Invalid email
    resp1 = await client.post(
        "/api/v1/auth/signup",
        json={"email": "invalid-email", "password": "Password123!"},
    )
    assert resp1.status_code == 422

    # Short password (< 8 chars)
    resp2 = await client.post(
        "/api/v1/auth/signup",
        json={"email": "valid@example.com", "password": "short"},
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_user_login_success(client: AsyncClient, test_user: User) -> None:
    """Test successful login returns valid JWT access token."""
    login_payload = {
        "email": test_user.email,
        "password": "Password123!",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == test_user.email
    assert "password" not in data["user"]


@pytest.mark.asyncio
async def test_user_login_invalid_credentials(client: AsyncClient, test_user: User) -> None:
    """Test login rejection on incorrect password or non-existent user."""
    # Wrong password
    resp1 = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "WrongPassword999!"},
    )
    assert resp1.status_code == 401
    assert "invalid email or password" in resp1.json()["detail"].lower()

    # Unknown email
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "Password123!"},
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_profile(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Test retrieving authenticated user profile."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email


@pytest.mark.asyncio
async def test_get_current_user_unauthorized(client: AsyncClient) -> None:
    """Test accessing protected route without or with invalid token."""
    # Missing token
    resp1 = await client.get("/api/v1/auth/me")
    assert resp1.status_code == 403 or resp1.status_code == 401

    # Invalid token
    resp2 = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token_xyz"}
    )
    assert resp2.status_code == 401
