from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_funcionarios_sem_autenticacao(client):
    response = await client.get("/funcionarios")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_operador_nao_pode_acessar_funcionarios(client_operador):
    response = await client_operador.get("/funcionarios")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_pode_acessar_funcionarios(client_admin, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "listar_funcionarios_ativos",
        AsyncMock(return_value=[]),
    )

    response = await client_admin.get("/funcionarios")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_operador_nao_pode_acessar_manutencoes(client_operador):
    response = await client_operador.get("/manutencoes")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manutencao_pode_acessar_manutencoes(
    client_manutencao,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module.repository,
        "listar_manutencoes_detalhadas",
        AsyncMock(return_value=[]),
    )

    response = await client_manutencao.get("/manutencoes")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_pode_acessar_manutencoes(client_admin, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "listar_manutencoes_detalhadas",
        AsyncMock(return_value=[]),
    )

    response = await client_admin.get("/manutencoes")

    assert response.status_code == 200