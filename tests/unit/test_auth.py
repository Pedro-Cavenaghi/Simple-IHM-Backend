
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth
from app.models import FuncionarioResponse


def criar_credenciais(token):
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )


def criar_funcionario():
    return {
        "id": 1,
        "nome": "João Silva",
        "cargo": "Operador",
        "turno_trabalho": 1,
        "ativo": True,
        "email": "joao@email.com",
        "perfil": "ADMIN",
    }


# API KEY


@pytest.mark.asyncio
async def test_verificar_api_key_valida():
    resultado = await auth.verificar_api_key(auth.API_KEY)

    assert resultado == auth.API_KEY


@pytest.mark.asyncio
async def test_verificar_api_key_invalida():
    with pytest.raises(HTTPException) as exc_info:
        await auth.verificar_api_key("chave-incorreta")

    assert exc_info.value.status_code == 401


# OBTENÇÃO DO USUÁRIO ATUAL


@pytest.mark.asyncio
async def test_obter_usuario_atual_com_sucesso(monkeypatch):
    funcionario = criar_funcionario()
    mock_repository = AsyncMock(return_value=funcionario)

    monkeypatch.setattr(
        auth.repository,
        "obter_funcionario_por_id",
        mock_repository,
    )

    token = auth.criar_token_acesso({"sub": "1"})
    credentials = criar_credenciais(token)
    conn = object()

    resultado = await auth.obter_usuario_atual(credentials, conn)

    assert isinstance(resultado, FuncionarioResponse)
    assert resultado.id == 1
    assert resultado.nome == "João Silva"
    assert resultado.perfil == "ADMIN"

    mock_repository.assert_awaited_once_with(conn, 1)


@pytest.mark.asyncio
async def test_obter_usuario_atual_sem_sub():
    token = auth.criar_token_acesso({"perfil": "ADMIN"})
    credentials = criar_credenciais(token)

    with pytest.raises(HTTPException) as exc_info:
        await auth.obter_usuario_atual(credentials, object())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_obter_usuario_atual_com_sub_invalido():
    token = auth.criar_token_acesso({"sub": "texto-invalido"})
    credentials = criar_credenciais(token)

    with pytest.raises(HTTPException) as exc_info:
        await auth.obter_usuario_atual(credentials, object())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_obter_usuario_atual_com_token_invalido():
    credentials = criar_credenciais("token-invalido")

    with pytest.raises(HTTPException) as exc_info:
        await auth.obter_usuario_atual(credentials, object())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_obter_usuario_atual_com_usuario_inexistente(monkeypatch):
    mock_repository = AsyncMock(return_value=None)

    monkeypatch.setattr(
        auth.repository,
        "obter_funcionario_por_id",
        mock_repository,
    )

    token = auth.criar_token_acesso({"sub": "999"})
    credentials = criar_credenciais(token)
    conn = object()

    with pytest.raises(HTTPException) as exc_info:
        await auth.obter_usuario_atual(credentials, conn)

    assert exc_info.value.status_code == 401
    mock_repository.assert_awaited_once_with(conn, 999)


# CONTROLE DE PERMISSÕES


def test_permissao_requerida_permite_perfil_autorizado():
    funcionario = FuncionarioResponse(**criar_funcionario())
    permissao = auth.PermissaoRequerida(["ADMIN"])

    resultado = permissao(funcionario)

    assert resultado == funcionario


def test_permissao_requerida_bloqueia_perfil_nao_autorizado():
    funcionario = FuncionarioResponse(**criar_funcionario())
    funcionario.perfil = "OPERADOR"

    permissao = auth.PermissaoRequerida(["ADMIN"])

    with pytest.raises(HTTPException) as exc_info:
        permissao(funcionario)

    assert exc_info.value.status_code == 403
