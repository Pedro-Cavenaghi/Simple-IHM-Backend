from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_listar_funcionarios(client, monkeypatch):
    funcionarios = [
        {
            "id": 1,
            "nome": "João Silva",
            "cargo": "Técnico",
            "turno_trabalho": 1,
            "ativo": True,
            "email": "joao@empresa.com",
        }
    ]

    monkeypatch.setattr(
        main_module.repository,
        "listar_funcionarios_ativos",
        AsyncMock(return_value=funcionarios),
    )

    response = await client.get("/funcionarios")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["nome"] == "João Silva"
    assert response.json()[0]["ativo"] is True


@pytest.mark.asyncio
async def test_obter_funcionario_por_id(client, monkeypatch):
    funcionario = {
        "id": 1,
        "nome": "João Silva",
        "cargo": "Técnico",
        "turno_trabalho": 1,
        "ativo": True,
        "email": "joao@empresa.com",
    }

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_id",
        AsyncMock(return_value=funcionario),
    )

    response = await client.get("/funcionarios/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["email"] == "joao@empresa.com"


@pytest.mark.asyncio
async def test_obter_funcionario_inexistente(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_id",
        AsyncMock(return_value=None),
    )

    response = await client.get("/funcionarios/999")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Funcionário não encontrado ou inativo."
    )


@pytest.mark.asyncio
async def test_cadastrar_funcionario(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "cadastrar_funcionario",
        AsyncMock(return_value=10),
    )

    response = await client.post(
        "/funcionarios",
        json={
            "nome": "Maria Souza",
            "cargo": "Operadora",
            "turno_trabalho": 2,
            "email": "MARIA@EMPRESA.COM",
            "senha": "123456",
        },
    )

    assert response.status_code == 201

    dados = response.json()

    assert dados["id"] == 10
    assert dados["nome"] == "Maria Souza"
    assert dados["email"] == "maria@empresa.com"
    assert dados["ativo"] is True


@pytest.mark.asyncio
async def test_cadastrar_funcionario_email_invalido(client):
    response = await client.post(
        "/funcionarios",
        json={
            "nome": "Maria Souza",
            "cargo": "Operadora",
            "turno_trabalho": 2,
            "email": "email-invalido",
            "senha": "123456",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cadastrar_funcionario_senha_curta(client):
    response = await client.post(
        "/funcionarios",
        json={
            "nome": "Maria Souza",
            "cargo": "Operadora",
            "turno_trabalho": 2,
            "email": "maria@empresa.com",
            "senha": "123",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_atualizar_funcionario(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "atualizar_funcionario",
        AsyncMock(return_value=True),
    )

    response = await client.put(
        "/funcionarios/1",
        json={
            "nome": "João Atualizado",
            "cargo": "Supervisor",
            "turno_trabalho": 3,
            "email": "joao.atualizado@empresa.com",
            "ativo": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "João Atualizado"
    assert response.json()["cargo"] == "Supervisor"


@pytest.mark.asyncio
async def test_atualizar_funcionario_inexistente(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "atualizar_funcionario",
        AsyncMock(return_value=False),
    )

    response = await client.put(
        "/funcionarios/999",
        json={
            "nome": "João Atualizado",
            "cargo": "Supervisor",
            "turno_trabalho": 3,
            "email": "joao.atualizado@empresa.com",
            "ativo": True,
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deletar_funcionario(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_funcionario",
        AsyncMock(return_value=True),
    )

    response = await client.delete("/funcionarios/1")

    assert response.status_code == 200
    assert response.json()["status"] == "Sucesso"


@pytest.mark.asyncio
async def test_deletar_funcionario_inexistente(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_funcionario",
        AsyncMock(return_value=False),
    )

    response = await client.delete("/funcionarios/999")

    assert response.status_code == 404