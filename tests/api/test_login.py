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
        "perfil": "ADMIN",
        "ativo": True,
    }

    mock_repository = AsyncMock(return_value=funcionario)
    mock_auditoria = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    monkeypatch.setattr(
        main_module.repository,
        "registrar_auditoria",
        mock_auditoria,
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
    assert dados["token_type"] == "bearer"
    assert "access_token" in dados

    assert dados["usuario"]["id"] == 1
    assert dados["usuario"]["nome"] == "João Silva"
    assert dados["usuario"]["email"] == "joao@email.com"
    assert dados["usuario"]["perfil"] == "ADMIN"

    mock_repository.assert_awaited_once_with(
        ANY,
        "joao@email.com",
    )

    mock_auditoria.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_normaliza_email(client, monkeypatch):
    senha_hash = main_module.pwd_context.hash("123456")

    funcionario = {
        "id": 1,
        "nome": "João Silva",
        "email": "joao@email.com",
        "senha_hash": senha_hash,
        "perfil": "ADMIN",
        "ativo": True,
    }

    mock_repository = AsyncMock(return_value=funcionario)
    mock_auditoria = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    monkeypatch.setattr(
        main_module.repository,
        "registrar_auditoria",
        mock_auditoria,
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
        "perfil": "OPERADOR",
        "ativo": True,
    }

    mock_repository = AsyncMock(return_value=funcionario)
    mock_auditoria = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "obter_funcionario_por_email",
        mock_repository,
    )

    monkeypatch.setattr(
        main_module.repository,
        "registrar_auditoria",
        mock_auditoria,
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
    mock_auditoria.assert_awaited_once()