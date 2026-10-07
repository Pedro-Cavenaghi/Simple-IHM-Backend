import asyncpg
import pytest

import app.repository as repository


@pytest.mark.asyncio
async def test_cadastrar_e_obter_funcionario(db_conn):
    dados = {
        "nome": "João Silva",
        "cargo": "Operador",
        "turno_trabalho": 1,
        "email": "JOAO@EMAIL.COM",
        "senha_hash": "hash_teste",
        "ativo": True,
    }

    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        dados,
    )

    assert funcionario_id is not None
    assert funcionario_id == 1

    funcionario = await repository.obter_funcionario_por_id(
        db_conn,
        funcionario_id,
    )

    assert funcionario is not None
    assert funcionario["id"] == 1
    assert funcionario["nome"] == "João Silva"
    assert funcionario["cargo"] == "Operador"
    assert funcionario["turno_trabalho"] == 1
    assert funcionario["email"] == "joao@email.com"
    assert funcionario["ativo"] is True


@pytest.mark.asyncio
async def test_listar_funcionarios(db_conn):
    await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Carlos Silva",
            "cargo": "Técnico",
            "turno_trabalho": 2,
            "email": "carlos@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Ana Souza",
            "cargo": "Operadora",
            "turno_trabalho": 1,
            "email": "ana@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    funcionarios = await repository.listar_funcionarios_ativos(db_conn)

    assert len(funcionarios) == 2

    # O repository ordena por nome ASC
    assert funcionarios[0]["nome"] == "Ana Souza"
    assert funcionarios[1]["nome"] == "Carlos Silva"


@pytest.mark.asyncio
async def test_buscar_funcionario_por_email(db_conn):
    await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Silva",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash_secreto",
            "ativo": True,
        },
    )

    funcionario = await repository.obter_funcionario_por_email(
        db_conn,
        "JOAO@EMAIL.COM",
    )

    assert funcionario is not None
    assert funcionario["nome"] == "João Silva"
    assert funcionario["email"] == "joao@email.com"
    assert funcionario["senha_hash"] == "hash_secreto"


@pytest.mark.asyncio
async def test_atualizar_funcionario(db_conn):
    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Silva",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    sucesso = await repository.atualizar_funcionario(
        db_conn,
        funcionario_id,
        {
            "nome": "João Atualizado",
            "cargo": "Supervisor",
            "turno_trabalho": 2,
            "email": "joao.novo@email.com",
        },
    )

    assert sucesso is True

    funcionario = await repository.obter_funcionario_por_id(
        db_conn,
        funcionario_id,
    )

    assert funcionario["nome"] == "João Atualizado"
    assert funcionario["cargo"] == "Supervisor"
    assert funcionario["turno_trabalho"] == 2
    assert funcionario["email"] == "joao.novo@email.com"


@pytest.mark.asyncio
async def test_atualizar_funcionario_inexistente(db_conn):
    sucesso = await repository.atualizar_funcionario(
        db_conn,
        999,
        {
            "nome": "Funcionário Inexistente",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "inexistente@email.com",
        },
    )

    assert sucesso is False


@pytest.mark.asyncio
async def test_soft_delete_funcionario(db_conn):
    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Silva",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    sucesso = await repository.soft_delete_funcionario(
        db_conn,
        funcionario_id,
    )

    assert sucesso is True

    funcionario = await repository.obter_funcionario_por_id(
        db_conn,
        funcionario_id,
    )

    assert funcionario is None


@pytest.mark.asyncio
async def test_soft_delete_funcionario_ja_removido(db_conn):
    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Silva",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    await repository.soft_delete_funcionario(
        db_conn,
        funcionario_id,
    )

    segunda_tentativa = await repository.soft_delete_funcionario(
        db_conn,
        funcionario_id,
    )

    assert segunda_tentativa is False


@pytest.mark.asyncio
async def test_nao_permite_email_duplicado(db_conn):
    await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Silva",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    segundo_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Outro João",
            "cargo": "Técnico",
            "turno_trabalho": 2,
            "email": "JOAO@EMAIL.COM",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    # O repository captura a exceção e retorna None.
    assert segundo_id is None


@pytest.mark.asyncio
async def test_permite_reutilizar_email_apos_soft_delete(db_conn):
    primeiro_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Antigo",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    await repository.soft_delete_funcionario(
        db_conn,
        primeiro_id,
    )

    novo_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "João Novo",
            "cargo": "Operador",
            "turno_trabalho": 1,
            "email": "joao@email.com",
            "senha_hash": "hash",
            "ativo": True,
        },
    )

    assert novo_id is not None
    assert novo_id != primeiro_id