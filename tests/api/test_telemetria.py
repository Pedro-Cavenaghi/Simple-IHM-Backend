from datetime import datetime
from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_listar_status_maquinas(client, monkeypatch):
    maquinas = [
        {
            "maquina_id": 1,
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "status_atual": "Ativa",
            "vibracao_rms": 1.5,
            "corrente_ampere": 10.0,
            "tensao_volt": 220.0,
            "potencia_watt": 2000.0,
            "frequencia_hz": 60.0,
            "momento_da_leitura": datetime(2026, 10, 7, 8, 0, 0),
        }
    ]

    mock_repository = AsyncMock(return_value=maquinas)

    monkeypatch.setattr(
        main_module.repository,
        "obter_status_atual",
        mock_repository,
    )

    response = await client.get("/status-maquinas")

    dados = response.json()

    assert response.status_code == 200
    assert len(dados) == 1
    assert dados[0]["maquina_id"] == 1
    assert dados[0]["status_atual"] == "Ativa"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_listar_status_por_id(client, monkeypatch):
    maquina = {
        "maquina_id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "status_atual": "Ativa",
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "momento_da_leitura": datetime(2026, 10, 7, 8, 0, 0),
    }

    mock_repository = AsyncMock(return_value=maquina)

    monkeypatch.setattr(
        main_module.repository,
        "obter_status_por_id",
        mock_repository,
    )

    response = await client.get("/status-maquinas/1")

    dados = response.json()

    assert response.status_code == 200
    assert dados["maquina_id"] == 1
    assert dados["status_atual"] == "Ativa"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_listar_status_por_id_inexistente(client, monkeypatch):
    mock_repository = AsyncMock(return_value=None)

    monkeypatch.setattr(
        main_module.repository,
        "obter_status_por_id",
        mock_repository,
    )

    response = await client.get("/status-maquinas/999")

    dados = response.json()

    assert response.status_code == 404
    assert dados["detail"] == "Status da máquina não encontrado."

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_enviar_dados_com_sucesso(client, monkeypatch):
    mock_repository = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "salvar_leitura",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ativa",
    }

    response = await client.post(
        "/enviar-dados",
        json=payload,
    )

    dados = response.json()

    assert response.status_code == 200
    assert dados["status"] == "Sucesso"
    assert dados["mensagem"] == "Dados gravados"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_enviar_dados_com_erro_no_repository(client, monkeypatch):
    mock_repository = AsyncMock(return_value=False)

    monkeypatch.setattr(
        main_module.repository,
        "salvar_leitura",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ativa",
    }

    response = await client.post(
        "/enviar-dados",
        json=payload,
    )

    dados = response.json()

    assert response.status_code == 500
    assert dados["detail"] == (
        "Erro ao gravar os dados de telemetria no banco"
    )

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_enviar_dados_com_tensao_invalida(client, monkeypatch):
    mock_repository = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "salvar_leitura",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 500.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ativa",
    }

    response = await client.post(
        "/enviar-dados",
        json=payload,
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_enviar_dados_com_maquina_id_invalido(client, monkeypatch):
    mock_repository = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "salvar_leitura",
        mock_repository,
    )

    payload = {
        "maquina_id": 0,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ativa",
    }

    response = await client.post(
        "/enviar-dados",
        json=payload,
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_enviar_dados_com_status_invalido(client, monkeypatch):
    mock_repository = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "salvar_leitura",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ligada",
    }

    response = await client.post(
        "/enviar-dados",
        json=payload,
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()