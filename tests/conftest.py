import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import auth
from app.database import get_db
from app.main import app
from app.models import FuncionarioResponse


async def override_get_db():
    yield object()


async def override_admin():
    return FuncionarioResponse(
        id=2,
        nome="Administrador Teste",
        cargo="Administrador",
        turno_trabalho=1,
        ativo=True,
        email="admin@teste.com",
        perfil="ADMIN",
    )


async def override_operador():
    return FuncionarioResponse(
        id=3,
        nome="Operador Teste",
        cargo="Operador",
        turno_trabalho=1,
        ativo=True,
        email="operador@teste.com",
        perfil="OPERADOR",
    )


async def override_manutencao():
    return FuncionarioResponse(
        id=4,
        nome="Técnico Teste",
        cargo="Técnico",
        turno_trabalho=1,
        ativo=True,
        email="manutencao@teste.com",
        perfil="MANUTENCAO",
    )


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
async def client_admin():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth.obter_usuario_atual] = override_admin

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_operador():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth.obter_usuario_atual] = override_operador

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_manutencao():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth.obter_usuario_atual] = override_manutencao

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()