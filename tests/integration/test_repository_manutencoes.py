from datetime import date

import pytest

import app.repository as repository


async def criar_maquina(db_conn):
    return await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )


async def criar_funcionario(db_conn):
    return await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Carlos Técnico",
            "cargo": "Técnico",
            "turno_trabalho": 1,
            "email": "carlos@email.com",
            "senha_hash": "hash_teste",
            "ativo": True,
            "perfil": "MANUTENCAO",
        },
    )


@pytest.mark.asyncio
async def test_agendar_e_obter_manutencao(db_conn):
    maquina = await criar_maquina(db_conn)

    manutencao_criada = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    assert manutencao_criada is not None
    assert manutencao_criada["id"] == 1
    assert manutencao_criada["maquina_id"] == maquina["id"]

    manutencao = await repository.obter_manutencao_por_id(
        db_conn,
        manutencao_criada["id"],
    )

    assert manutencao is not None
    assert manutencao["id"] == 1
    assert manutencao["maquina_id"] == maquina["id"]
    assert manutencao["tag_maquina"] == "INJ-01"
    assert manutencao["nome_maquina"] == "Injetora 01"
    assert manutencao["descricao_servico"] == "Troca preventiva de rolamento"
    assert manutencao["concluida"] is False
    assert manutencao["tipo_manutencao"] == "Preventiva"


@pytest.mark.asyncio
async def test_agendar_manutencao_maquina_inexistente(db_conn):
    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": 999,
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    assert manutencao is None


@pytest.mark.asyncio
async def test_listar_manutencoes_detalhadas(db_conn):
    maquina = await criar_maquina(db_conn)

    await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Análise de vibração",
            "data_agendada": date(2026, 10, 25),
            "tipo_manutencao": "Preditiva",
        },
    )

    manutencoes = await repository.listar_manutencoes_detalhadas(db_conn)

    assert len(manutencoes) == 2
    assert manutencoes[0]["tag_maquina"] == "INJ-01"
    assert manutencoes[0]["concluida"] is False
    assert manutencoes[1]["concluida"] is False


@pytest.mark.asyncio
async def test_obter_manutencao_inexistente(db_conn):
    manutencao = await repository.obter_manutencao_por_id(
        db_conn,
        999,
    )

    assert manutencao is None


@pytest.mark.asyncio
async def test_atualizar_manutencao(db_conn):
    maquina = await criar_maquina(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    sucesso = await repository.atualizar_dados_manutencao(
        db_conn,
        manutencao_id,
        {
            "descricao_servico": "Inspeção completa do equipamento",
            "data_agendada": date(2026, 10, 30),
            "tipo_manutencao": "Preditiva",
        },
    )

    assert sucesso is True

    manutencao = await repository.obter_manutencao_por_id(
        db_conn,
        manutencao_id,
    )

    assert manutencao["descricao_servico"] == "Inspeção completa do equipamento"
    assert manutencao["data_agendada"] == date(2026, 10, 30)
    assert manutencao["tipo_manutencao"] == "Preditiva"


@pytest.mark.asyncio
async def test_concluir_manutencao(db_conn):
    maquina = await criar_maquina(db_conn)
    funcionario_id = await criar_funcionario(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    sucesso = await repository.concluir_ordem_manutencao(
        db_conn,
        manutencao_id,
        funcionario_id,
    )

    assert sucesso is True

    manutencao = await repository.obter_manutencao_por_id(
        db_conn,
        manutencao_id,
    )

    assert manutencao["concluida"] is True
    assert manutencao["data_conclusao_real"] is not None
    assert manutencao["funcionario_id"] == funcionario_id
    assert manutencao["nome_funcionario"] == "Carlos Técnico"


@pytest.mark.asyncio
async def test_nao_concluir_manutencao_duas_vezes(db_conn):
    maquina = await criar_maquina(db_conn)
    funcionario_id = await criar_funcionario(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    primeira = await repository.concluir_ordem_manutencao(
        db_conn,
        manutencao_id,
        funcionario_id,
    )

    segunda = await repository.concluir_ordem_manutencao(
        db_conn,
        manutencao_id,
        funcionario_id,
    )

    assert primeira is True
    assert segunda is False


@pytest.mark.asyncio
async def test_nao_atualizar_manutencao_concluida(db_conn):
    maquina = await criar_maquina(db_conn)
    funcionario_id = await criar_funcionario(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    await repository.concluir_ordem_manutencao(
        db_conn,
        manutencao_id,
        funcionario_id,
    )

    sucesso = await repository.atualizar_dados_manutencao(
        db_conn,
        manutencao_id,
        {
            "descricao_servico": "Tentativa de alteração",
            "data_agendada": date(2026, 11, 1),
            "tipo_manutencao": "Preditiva",
        },
    )

    assert sucesso is False


@pytest.mark.asyncio
async def test_soft_delete_manutencao(db_conn):
    maquina = await criar_maquina(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    sucesso = await repository.soft_delete_manutencao(
        db_conn,
        manutencao_id,
    )

    assert sucesso is True

    manutencao = await repository.obter_manutencao_por_id(
        db_conn,
        manutencao_id,
    )

    assert manutencao is None


@pytest.mark.asyncio
async def test_nao_deletar_manutencao_concluida(db_conn):
    maquina = await criar_maquina(db_conn)
    funcionario_id = await criar_funcionario(db_conn)

    manutencao = await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 20),
            "tipo_manutencao": "Preventiva",
        },
    )

    manutencao_id = manutencao["id"]

    await repository.concluir_ordem_manutencao(
        db_conn,
        manutencao_id,
        funcionario_id,
    )

    sucesso = await repository.soft_delete_manutencao(
        db_conn,
        manutencao_id,
    )

    assert sucesso is False