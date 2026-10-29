import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLE_RESEARCHER
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app import models as _models
from app.models.user import User, Workspace

# Use a process-specific SQLite database so parallel test commands do not
# contend for the same file lock.
Path("tmp").mkdir(exist_ok=True)
TEST_DB_URL = f"sqlite+aiosqlite:///./tmp/test-{os.getpid()}.db"

from sqlalchemy import event

engine = create_async_engine(TEST_DB_URL, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
test_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        username="testadmin",
        hashed_password=hash_password("admin123"),
        role=ROLE_ADMIN,
    )
    db.add(user)
    await db.flush()
    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    return create_access_token(admin_user.id)


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def researcher_user(db: AsyncSession) -> User:
    user = User(
        username="researcher1",
        hashed_password=hash_password("pass123"),
        role=ROLE_RESEARCHER,
    )
    db.add(user)
    await db.flush()
    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def researcher_token(researcher_user: User) -> str:
    return create_access_token(researcher_user.id)


@pytest_asyncio.fixture
async def researcher_headers(researcher_token: str) -> dict:
    return {"Authorization": f"Bearer {researcher_token}"}


@pytest_asyncio.fixture
async def pi_user(db: AsyncSession) -> User:
    user = User(
        username="pi1",
        hashed_password=hash_password("pass123"),
        role=ROLE_PI,
    )
    db.add(user)
    await db.flush()
    workspace = Workspace(researcher_id=user.id)
    db.add(workspace)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def pi_headers(pi_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(pi_user.id)}"}
