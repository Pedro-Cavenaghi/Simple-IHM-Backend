
import runpy
import warnings
from unittest.mock import AsyncMock, Mock

import pytest
import uvicorn

import app.main as main_module


@pytest.mark.asyncio
async def test_lifespan_conecta_e_desconecta_banco(monkeypatch):
    conectar = AsyncMock()
    desconectar = AsyncMock()

    monkeypatch.setattr(main_module.Database, "connect", conectar)
    monkeypatch.setattr(main_module.Database, "disconnect", desconectar)

    async with main_module.lifespan(main_module.app):
        conectar.assert_awaited_once()
        desconectar.assert_not_awaited()

    desconectar.assert_awaited_once()


@pytest.mark.asyncio
async def test_rota_raiz(client):
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "mensagem": "API Simple IHM Ativa (Assíncrona)"
    }


@pytest.mark.asyncio
async def test_documentacao_swagger(client):
    response = await client.get("/docs")

    assert response.status_code == 200
    assert "Simple IHM API - Swagger UI" in response.text


@pytest.mark.asyncio
async def test_favicon(client, monkeypatch, tmp_path):
    diretorio_app = tmp_path / "app"
    diretorio_app.mkdir()

    favicon = tmp_path / "favicon.ico"
    favicon.write_bytes(b"icone-de-teste")

    monkeypatch.setattr(
        main_module,
        "BASE_DIR",
        str(diretorio_app),
    )

    response = await client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.content == b"icone-de-teste"


@pytest.mark.asyncio
async def test_listar_auditoria(client_admin, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "listar_logs_auditoria",
        mock_repository,
    )

    response = await client_admin.get(
        "/auditoria?usuario_id=2&limite=10"
    )

    assert response.status_code == 200
    assert response.json() == []

    mock_repository.assert_awaited_once()
    assert mock_repository.await_args.kwargs == {
        "usuario_id": 2,
        "limite": 10,
    }


def test_execucao_direta_da_aplicacao(monkeypatch):
    mock_run = Mock()

    monkeypatch.setattr(uvicorn, "run", mock_run)
    monkeypatch.setenv("PORT", "8765")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)

        runpy.run_module(
            "app.main",
            run_name="__main__",
        )

    mock_run.assert_called_once_with(
        "app.main:app",
        host="0.0.0.0",
        port=8765,
    )
