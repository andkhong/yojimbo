"""Shared test fixtures."""

from datetime import time

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models.appointment import TimeSlot
from app.models.department import Department
from app.models.user import DashboardUser
from app.core.security import hash_password

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    """Provide a clean database session for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionFactory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    """Provide an async HTTP test client with the test database."""
    from app.main import app

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_db(db: AsyncSession):
    """Provide a database with sample departments and an admin user."""
    dept = Department(
        name="Building Permits",
        code="BLDG",
        description="Building permits and inspections",
        operating_hours='{"mon-fri": "9:00-16:00"}',
    )
    db.add(dept)
    await db.flush()

    # Add time slots for Monday-Friday
    for day in range(5):
        slot = TimeSlot(
            department_id=dept.id,
            day_of_week=day,
            start_time=time(9, 0),
            end_time=time(16, 0),
            slot_duration_minutes=30,
            max_concurrent=2,
        )
        db.add(slot)

    admin = DashboardUser(
        username="admin",
        password_hash=hash_password("admin"),
        name="Test Admin",
        role="admin",
    )
    db.add(admin)
    await db.commit()

    return db


@pytest_asyncio.fixture
async def seeded_client(seeded_db: AsyncSession):
    """Async HTTP client wired to a seeded database."""
    from app.main import app

    async def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
