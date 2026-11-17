from unittest.mock import AsyncMock

import pytest

import app.main as main_module
from app import auth


@pytest.mark.asyncio
async def test_listar_maquinas_para_dispositivos(client, monkeypatch):
    maquinas = [
        {
            "id": 1,
            "tag_maquina": "CNC-01",
            "nome_maquina": "Torno CNC",
            "setor": "Usinagem",
            "em_manutencao": False,
        },
        {
            "id": 2,
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "setor": None,
            "em_manutencao": True,
        },
    ]

    mock_repository = AsyncMock(return_value=maquinas)

    monkeypatch.setattr(
        main_module.repository,
        "listar_maquinas_para_dispositivos",
        mock_repository,
    )

    response = await client.get(
        "/dispositivos/maquinas",
        headers={"X-API-Key": auth.API_KEY},
    )

    dados = response.json()

    assert response.status_code == 200
    assert len(dados) == 2
    assert dados[0]["tag_maquina"] == "CNC-01"
    assert dados[0]["em_manutencao"] is False
    assert dados[1]["em_manutencao"] is True

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_listar_maquinas_para_dispositivos_sem_api_key(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "listar_maquinas_para_dispositivos",
        mock_repository,
    )

    response = await client.get("/dispositivos/maquinas")

    assert response.status_code == 401
    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_listar_maquinas_para_dispositivos_com_api_key_invalida(
    client, monkeypatch
):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "listar_maquinas_para_dispositivos",
        mock_repository,
    )

    response = await client.get(
        "/dispositivos/maquinas",
        headers={"X-API-Key": "chave-errada"},
    )

    assert response.status_code == 401
    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_listar_maquinas_para_dispositivos_nao_aceita_jwt(client_admin):
    """Um usuário logado não substitui a API Key do dispositivo."""
    response = await client_admin.get("/dispositivos/maquinas")

    assert response.status_code == 401
