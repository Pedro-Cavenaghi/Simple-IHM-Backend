import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
import os
import asyncpg



async def override_get_db():
    yield object()


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_conn():
    conn = await asyncpg.connect(
        host=os.getenv("TEST_DB_HOST", "localhost"),
        port=int(os.getenv("TEST_DB_PORT", "5433")),
        user=os.getenv("TEST_DB_USER", "test_user"),
        password=os.getenv("TEST_DB_PASSWORD", "test_password"),
        database=os.getenv("TEST_DB_NAME", "simple_ihm_test"),
    )

    await conn.execute(
        """
        TRUNCATE TABLE
            logs_maquinas,
            status_atual_maquinas,
            manutencao_preventiva,
            funcionarios,
            maquinas
        RESTART IDENTITY CASCADE;
        """
    )

    yield conn

    await conn.execute(
        """
        TRUNCATE TABLE
            logs_maquinas,
            status_atual_maquinas,
            manutencao_preventiva,
            funcionarios,
            maquinas
        RESTART IDENTITY CASCADE;
        """
    )

    await conn.close()