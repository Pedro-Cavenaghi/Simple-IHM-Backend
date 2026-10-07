from unittest.mock import ANY, AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_login_com_sucesso(client, monkeypatch):
    senha_hash = main_module.pwd_context.hash("123456")

    funcionario = {
        "id": 1,
        "nome": "João Silva",
        "email": "joao@email.com",
        "senha_hash": senha_hash,
    }

    mock_repository = AsyncMock(return_value=funcionario)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    response = await client.post(
        "/login",
        json={
            "email": "joao@email.com",
            "senha": "123456",
        },
    )

    dados = response.json()

    assert response.status_code == 200
    assert dados["status"] == "Sucesso"
    assert dados["usuario_id"] == 1
    assert dados["nome"] == "João Silva"

    mock_repository.assert_awaited_once_with(
        ANY,
        "joao@email.com",
    )


@pytest.mark.asyncio
async def test_login_normaliza_email(client, monkeypatch):
    senha_hash = main_module.pwd_context.hash("123456")

    funcionario = {
        "id": 1,
        "nome": "João Silva",
        "email": "joao@email.com",
        "senha_hash": senha_hash,
    }

    mock_repository = AsyncMock(return_value=funcionario)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    response = await client.post(
        "/login",
        json={
            "email": "  JOAO@EMAIL.COM  ",
            "senha": "123456",
        },
    )

    assert response.status_code == 200

    mock_repository.assert_awaited_once_with(
        ANY,
        "joao@email.com",
    )


@pytest.mark.asyncio
async def test_login_usuario_inexistente(client, monkeypatch):
    mock_repository = AsyncMock(return_value=None)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    response = await client.post(
        "/login",
        json={
            "email": "naoexiste@email.com",
            "senha": "123456",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciais inválidas"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_senha_incorreta(client, monkeypatch):
    senha_hash = main_module.pwd_context.hash("senha-correta")

    funcionario = {
        "id": 1,
        "nome": "João Silva",
        "email": "joao@email.com",
        "senha_hash": senha_hash,
    }

    mock_repository = AsyncMock(return_value=funcionario)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    response = await client.post(
        "/login",
        json={
            "email": "joao@email.com",
            "senha": "senha-errada",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciais inválidas"

    mock_repository.assert_awaited_once()