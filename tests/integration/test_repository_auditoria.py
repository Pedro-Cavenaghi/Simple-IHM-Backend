
from datetime import datetime, timedelta, timezone

import pytest
import app.repository as repository


async def criar_funcionario(conn, email):
    dados = {
        "nome": "Funcionario Teste",
        "cargo": "Operador",
        "turno_trabalho": 1,
        "email": email,
        "senha_hash": "hash_teste",
        "ativo": True,
    }

    funcionario_id = await repository.cadastrar_funcionario(conn, dados)

    assert funcionario_id is not None

    return funcionario_id


@pytest.mark.asyncio
async def test_registrar_auditoria_com_usuario(db_conn):
    funcionario_id = await criar_funcionario(
        db_conn, "auditoria1@teste.com"
    )

    resultado = await repository.registrar_auditoria(
        db_conn,
        funcionario_id,
        "CRIAR",
        "MAQUINA",
        10,
        "Máquina cadastrada",
    )

    assert resultado is True

    registros = await repository.listar_logs_auditoria(
        db_conn, usuario_id=funcionario_id
    )

    assert len(registros) == 1

    registro = registros[0]

    assert registro["usuario_id"] == funcionario_id
    assert registro["usuario_nome"] == "Funcionario Teste"
    assert registro["usuario_email"] == "auditoria1@teste.com"
    assert registro["acao"] == "CRIAR"
    assert registro["entidade"] == "MAQUINA"
    assert registro["entidade_id"] == 10
    assert registro["detalhes"] == "Máquina cadastrada"
    assert registro["criado_em"] is not None


@pytest.mark.asyncio
async def test_registrar_auditoria_sem_usuario(db_conn):
    resultado = await repository.registrar_auditoria(
        db_conn,
        None,
        "SISTEMA",
        "TELEMETRIA",
        5,
        "Registro automático",
    )

    assert resultado is True

    registros = await repository.listar_logs_auditoria(db_conn)

    assert len(registros) == 1

    registro = registros[0]

    assert registro["usuario_id"] is None
    assert registro["usuario_nome"] is None
    assert registro["usuario_email"] is None
    assert registro["acao"] == "SISTEMA"


@pytest.mark.asyncio
async def test_listar_logs_auditoria_filtrando_por_usuario(db_conn):
    funcionario1 = await criar_funcionario(
        db_conn, "auditoria2@teste.com"
    )
    funcionario2 = await criar_funcionario(
        db_conn, "auditoria3@teste.com"
    )

    await repository.registrar_auditoria(
        db_conn, funcionario1, "CRIAR", "MAQUINA"
    )
    await repository.registrar_auditoria(
        db_conn, funcionario1, "ATUALIZAR", "MAQUINA"
    )
    await repository.registrar_auditoria(
        db_conn, funcionario2, "EXCLUIR", "MAQUINA"
    )
    await repository.registrar_auditoria(
        db_conn, None, "SISTEMA", "TELEMETRIA"
    )

    todos = await repository.listar_logs_auditoria(db_conn)
    filtrados = await repository.listar_logs_auditoria(
        db_conn, usuario_id=funcionario1
    )

    assert len(todos) == 4
    assert len(filtrados) == 2

    assert all(
        registro["usuario_id"] == funcionario1
        for registro in filtrados
    )


@pytest.mark.asyncio
async def test_listar_logs_auditoria_respeita_limite_e_ordem(db_conn):
    for numero in range(1, 4):
        await repository.registrar_auditoria(
            db_conn,
            None,
            f"ACAO_{numero}",
            "TESTE",
        )

    registros_inseridos = await db_conn.fetch(
        "SELECT id FROM audit_logs ORDER BY id ASC"
    )

    data_base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for indice, registro in enumerate(registros_inseridos):
        await db_conn.execute(
            """
            UPDATE audit_logs
            SET criado_em = $1
            WHERE id = $2
            """,
            data_base + timedelta(days=indice),
            registro["id"],
        )

    registros = await repository.listar_logs_auditoria(
        db_conn, limite=2
    )

    assert len(registros) == 2
    assert registros[0]["acao"] == "ACAO_3"
    assert registros[1]["acao"] == "ACAO_2"


@pytest.mark.asyncio
async def test_auditoria_permanece_apos_exclusao_do_funcionario(db_conn):
    funcionario_id = await criar_funcionario(
        db_conn, "auditoria4@teste.com"
    )

    await repository.registrar_auditoria(
        db_conn,
        funcionario_id,
        "LOGIN",
        "FUNCIONARIO",
        funcionario_id,
        "Funcionário realizou login",
    )

    # A FK deve preservar a auditoria e definir usuario_id como NULL.
    await db_conn.execute(
        "DELETE FROM funcionarios WHERE id = $1",
        funcionario_id,
    )

    registros = await repository.listar_logs_auditoria(db_conn)

    assert len(registros) == 1

    registro = registros[0]

    assert registro["usuario_id"] is None
    assert registro["usuario_nome"] is None
    assert registro["usuario_email"] is None
    assert registro["acao"] == "LOGIN"
    assert registro["entidade"] == "FUNCIONARIO"
    assert registro["detalhes"] == "Funcionário realizou login"
