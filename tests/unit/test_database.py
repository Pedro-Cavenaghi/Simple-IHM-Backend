
import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import database, dbconfig


def test_db_uri_converte_esquema_postgres(monkeypatch):
    monkeypatch.setattr(
        dbconfig,
        "DATABASE_URL_RAILWAY",
        "postgres://usuario:senha@localhost:5432/simple_ihm",
    )

    spec = importlib.util.spec_from_file_location(
        "app.database_test",
        database.__file__,
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert modulo.DB_URI == (
        "postgresql://usuario:senha@localhost:5432/simple_ihm"
    )


def test_get_pool_retorna_pool_inicializado(monkeypatch):
    pool = object()
    monkeypatch.setattr(database.Database, "pool", pool)

    assert database.Database.get_pool() is pool


def test_get_pool_falha_quando_nao_inicializado(monkeypatch):
    monkeypatch.setattr(database.Database, "pool", None)

    with pytest.raises(RuntimeError, match="Pool de conexões não foi inicializado"):
        database.Database.get_pool()


@pytest.mark.asyncio
async def test_connect_inicializa_pool(monkeypatch):
    pool_fake = object()
    criar_pool = AsyncMock(return_value=pool_fake)

    monkeypatch.setattr(database.Database, "pool", None)
    monkeypatch.setattr(database.asyncpg, "create_pool", criar_pool)

    await database.Database.connect()

    criar_pool.assert_awaited_once_with(
        database.DB_URI,
        min_size=2,
        max_size=10,
    )
    assert database.Database.pool is pool_fake


@pytest.mark.asyncio
async def test_disconnect_fecha_pool(monkeypatch):
    pool_fake = MagicMock()
    pool_fake.close = AsyncMock()

    monkeypatch.setattr(database.Database, "pool", pool_fake)

    await database.Database.disconnect()

    pool_fake.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_nao_faz_nada_sem_pool(monkeypatch):
    monkeypatch.setattr(database.Database, "pool", None)

    await database.Database.disconnect()


@pytest.mark.asyncio
async def test_get_db_fornece_conexao(monkeypatch):
    conexao = object()

    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(return_value=conexao)
    contexto.__aexit__ = AsyncMock(return_value=False)

    pool_fake = MagicMock()
    pool_fake.acquire.return_value = contexto

    monkeypatch.setattr(database.Database, "pool", pool_fake)

    gerador = database.get_db()

    resultado = await anext(gerador)

    assert resultado is conexao
    pool_fake.acquire.assert_called_once()

    await gerador.aclose()

    contexto.__aexit__.assert_awaited_once()


def test_db_uri_preserva_url_postgresql(monkeypatch):
    url = "postgresql://usuario:senha@localhost:5432/simple_ihm"

    monkeypatch.setattr(
        dbconfig,
        "DATABASE_URL_RAILWAY",
        url,
    )

    spec = importlib.util.spec_from_file_location(
        "app.database_test",
        database.__file__,
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert modulo.DB_URI == url
