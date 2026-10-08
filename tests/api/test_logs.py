from datetime import datetime
from unittest.mock import ANY, AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_listar_logs(client, monkeypatch):
    logs = [
        {
            "id": 1,
            "horario_do_log": datetime(2026, 10, 7, 8, 0, 0),
            "maquina_id": 1,
            "turno": 1,
            "vibracao_rms": 1.5,
            "corrente_ampere": 10.0,
            "tensao_volt": 220.0,
            "potencia_watt": 2000.0,
            "status_no_momento": "Ativa",
            "frequencia_hz": 60.0,
        }
    ]

    mock_repository = AsyncMock(return_value=logs)

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get("/logs")

    dados = response.json()

    assert response.status_code == 200
    assert len(dados) == 1
    assert dados[0]["id"] == 1
    assert dados[0]["maquina_id"] == 1
    assert dados[0]["status_no_momento"] == "Ativa"

    mock_repository.assert_awaited_once_with(
        conn=ANY,
        maquina_id=None,
        periodo="hoje",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )


@pytest.mark.asyncio
async def test_listar_logs_filtrados_por_maquina(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get(
        "/logs",
        params={
            "maquina_id": 3,
            "periodo": "semana",
            "limite": 100,
        },
    )

    assert response.status_code == 200
    assert response.json() == []

    mock_repository.assert_awaited_once_with(
        conn=ANY,
        maquina_id=3,
        periodo="semana",
        data_inicio=None,
        data_fim=None,
        limite=100,
    )


@pytest.mark.asyncio
async def test_listar_logs_periodo_customizado(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get(
        "/logs",
        params={
            "periodo": "customizado",
            "data_inicio": "2026-10-01",
            "data_fim": "2026-10-07",
        },
    )

    assert response.status_code == 200

    mock_repository.assert_awaited_once_with(
        conn=ANY,
        maquina_id=None,
        periodo="customizado",
        data_inicio=ANY,
        data_fim=ANY,
        limite=500,
    )


@pytest.mark.asyncio
async def test_periodo_customizado_sem_datas(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get(
        "/logs",
        params={
            "periodo": "customizado",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Para buscas com o período 'customizado', você deve informar "
        "as datas de início e fim."
    )

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_logs_limite_acima_do_maximo(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get(
        "/logs",
        params={
            "limite": 1001,
        },
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_logs_limite_igual_a_zero(client, monkeypatch):
    mock_repository = AsyncMock(return_value=[])

    monkeypatch.setattr(
        main_module.repository,
        "buscar_historico_logs",
        mock_repository,
    )

    response = await client.get(
        "/logs",
        params={
            "limite": 0,
        },
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()