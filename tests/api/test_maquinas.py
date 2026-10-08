from datetime import datetime
from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_listar_maquinas(client, monkeypatch):
    maquinas = [
        {
            "id": 1,
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
            "data_cadastro": datetime(2026, 10, 6, 8, 0, 0),
        }
    ]

    mock_repository = AsyncMock(return_value=maquinas)

    monkeypatch.setattr(
        main_module.repository,
        "listar_maquinas_cadastradas",
        mock_repository,
    )

    response = await client.get("/maquinas")

    assert response.status_code == 200

    dados = response.json()

    assert len(dados) == 1
    assert dados[0]["id"] == 1
    assert dados[0]["tag_maquina"] == "INJ-01"
    assert dados[0]["nome_maquina"] == "Injetora 01"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_obter_maquina_por_id(client, monkeypatch):
    maquina = {
        "id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "setor": "Produção",
        "data_cadastro": datetime(2026, 10, 6, 8, 0, 0),
    }

    monkeypatch.setattr(
        main_module.repository,
        "obter_maquina_por_id",
        AsyncMock(return_value=maquina),
    )

    response = await client.get("/maquinas/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["tag_maquina"] == "INJ-01"


@pytest.mark.asyncio
async def test_obter_maquina_inexistente(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "obter_maquina_por_id",
        AsyncMock(return_value=None),
    )

    response = await client.get("/maquinas/999")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Máquina não encontrada ou já desativada."
    )


@pytest.mark.asyncio
async def test_cadastrar_maquina(client, monkeypatch):
    maquina_criada = {
        "id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "setor": "Produção",
        "data_cadastro": datetime(2026, 10, 6, 8, 0, 0),
    }

    mock_repository = AsyncMock(return_value=maquina_criada)

    monkeypatch.setattr(
        main_module.repository,
        "cadastrar_maquina",
        mock_repository,
    )

    response = await client.post(
        "/maquinas",
        json={
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == 1
    assert response.json()["tag_maquina"] == "INJ-01"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_atualizar_maquina(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "atualizar_maquina",
        AsyncMock(return_value=True),
    )

    response = await client.put(
        "/maquinas/1",
        json={
            "tag_maquina": "INJ-02",
            "nome_maquina": "Injetora Atualizada",
            "setor": "Montagem",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["tag_maquina"] == "INJ-02"
    assert response.json()["nome_maquina"] == "Injetora Atualizada"


@pytest.mark.asyncio
async def test_deletar_maquina(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_maquina",
        AsyncMock(return_value=True),
    )

    response = await client.delete("/maquinas/1")

    assert response.status_code == 200
    assert response.json()["status"] == "Sucesso"


@pytest.mark.asyncio
async def test_deletar_maquina_inexistente(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_maquina",
        AsyncMock(return_value=False),
    )

    response = await client.delete("/maquinas/999")

    assert response.status_code == 404