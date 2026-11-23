from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

import app.repository as repository

DESCRICAO = "Manutenção preditiva por provável sobrecarga: verificar a carga."


async def preparar(db_conn):
    maquina = await repository.cadastrar_maquina(
        db_conn,
        {"tag_maquina": "INJ-01", "nome_maquina": "Injetora 01", "setor": "Produção"},
    )
    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Técnico Teste",
            "cargo": "Técnico",
            "turno_trabalho": 1,
            "email": "tecnico@email.com",
            "senha_hash": "hash",
            "ativo": True,
            "perfil": "MANUTENCAO",
        },
    )
    return maquina["id"], funcionario_id


def dados(maquina_id, **extra):
    return {
        "maquina_id": maquina_id,
        "diagnostico": "sobrecarga",
        "confianca": 0.9,
        "pontuacao": 0.4,
        "severidade": "alta",
        "mensagem": "Provável sobrecarga.",
        "manutencao_descricao": DESCRICAO,
        **extra,
    }


@pytest.mark.asyncio
async def test_sem_diagnostico_nao_gera_solicitacao(db_conn):
    maquina_id, _ = await preparar(db_conn)

    alerta = await repository.criar_alerta(
        db_conn, dados(maquina_id, diagnostico=None, manutencao_descricao=None)
    )

    assert alerta["manutencao_status"] is None


@pytest.mark.asyncio
async def test_diagnostico_gera_solicitacao_sem_criar_ordem(db_conn):
    maquina_id, _ = await preparar(db_conn)

    alerta = await repository.criar_alerta(db_conn, dados(maquina_id))

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE;")
    assert alerta["manutencao_status"] == "pendente"
    assert alerta["manutencao_data_sugerida"] == hoje
    assert await repository.listar_manutencoes_detalhadas(db_conn) == []


@pytest.mark.asyncio
async def test_severidade_media_sugere_amanha(db_conn):
    maquina_id, _ = await preparar(db_conn)

    alerta = await repository.criar_alerta(
        db_conn, dados(maquina_id, severidade="media")
    )

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE;")
    assert alerta["manutencao_data_sugerida"] == hoje + timedelta(days=1)


@pytest.mark.asyncio
async def test_nao_duplica_solicitacao_pendente_da_maquina(db_conn):
    maquina_id, _ = await preparar(db_conn)
    primeiro = await repository.criar_alerta(db_conn, dados(maquina_id))
    await repository.encerrar_alerta(db_conn, primeiro["id"])

    segundo = await repository.criar_alerta(db_conn, dados(maquina_id))

    assert segundo["manutencao_status"] is None
    fila = await repository.listar_solicitacoes_manutencao(db_conn)
    assert [a["id"] for a in fila] == [primeiro["id"]]


@pytest.mark.asyncio
async def test_aprovar_cria_ordem_preditiva(db_conn):
    maquina_id, funcionario_id = await preparar(db_conn)
    alerta = await repository.criar_alerta(db_conn, dados(maquina_id))
    data = date(2030, 1, 15)

    aprovado = await repository.aprovar_manutencao_alerta(
        db_conn, alerta["id"], funcionario_id, data_agendada=data, observacao="Ok"
    )

    assert aprovado["manutencao_status"] == "aprovada"
    assert aprovado["analisado_por_nome"] == "Técnico Teste"
    ordem = await repository.obter_manutencao_por_id(db_conn, aprovado["manutencao_id"])
    assert ordem["tipo_manutencao"] == "Preditiva"
    assert ordem["data_agendada"] == data
    assert ordem["descricao_servico"] == DESCRICAO
    # Aprovar de novo não cria uma segunda ordem
    assert (
        await repository.aprovar_manutencao_alerta(
            db_conn, alerta["id"], funcionario_id
        )
        is None
    )
    assert len(await repository.listar_manutencoes_detalhadas(db_conn)) == 1


@pytest.mark.asyncio
async def test_ordem_preditiva_aberta_evita_nova_solicitacao(db_conn):
    maquina_id, funcionario_id = await preparar(db_conn)
    primeiro = await repository.criar_alerta(db_conn, dados(maquina_id))
    await repository.aprovar_manutencao_alerta(
        db_conn, primeiro["id"], funcionario_id, data_agendada=date(2030, 1, 15)
    )
    await repository.encerrar_alerta(db_conn, primeiro["id"])

    segundo = await repository.criar_alerta(db_conn, dados(maquina_id))

    assert segundo["manutencao_status"] is None


@pytest.mark.asyncio
async def test_falha_diferente_gera_nova_solicitacao(db_conn):
    maquina_id, _ = await preparar(db_conn)
    primeiro = await repository.criar_alerta(db_conn, dados(maquina_id))
    await repository.encerrar_alerta(db_conn, primeiro["id"])

    segundo = await repository.criar_alerta(
        db_conn, dados(maquina_id, diagnostico="desbalanceamento")
    )

    assert segundo["manutencao_status"] == "pendente"
    assert len(await repository.listar_solicitacoes_manutencao(db_conn)) == 2


@pytest.mark.asyncio
async def test_ordem_aberta_nao_bloqueia_falha_diferente(db_conn):
    maquina_id, funcionario_id = await preparar(db_conn)
    primeiro = await repository.criar_alerta(db_conn, dados(maquina_id))
    await repository.aprovar_manutencao_alerta(
        db_conn, primeiro["id"], funcionario_id, data_agendada=date(2030, 1, 15)
    )
    await repository.encerrar_alerta(db_conn, primeiro["id"])

    segundo = await repository.criar_alerta(
        db_conn, dados(maquina_id, diagnostico="queda_tensao")
    )

    assert segundo["manutencao_status"] == "pendente"


@pytest.mark.asyncio
async def test_ordem_concluida_libera_nova_solicitacao(db_conn):
    maquina_id, funcionario_id = await preparar(db_conn)
    primeiro = await repository.criar_alerta(db_conn, dados(maquina_id))
    aprovado = await repository.aprovar_manutencao_alerta(
        db_conn, primeiro["id"], funcionario_id
    )
    await repository.concluir_ordem_manutencao(
        db_conn, aprovado["manutencao_id"], funcionario_id
    )
    await repository.encerrar_alerta(db_conn, primeiro["id"])

    segundo = await repository.criar_alerta(db_conn, dados(maquina_id))

    assert segundo["manutencao_status"] == "pendente"


@pytest.mark.asyncio
async def test_erro_na_solicitacao_nao_deixa_alerta_orfao(db_conn, monkeypatch):
    maquina_id, _ = await preparar(db_conn)
    monkeypatch.setattr(
        repository,
        "_solicitar_manutencao",
        AsyncMock(side_effect=RuntimeError("falha simulada")),
    )

    assert await repository.criar_alerta(db_conn, dados(maquina_id)) is None
    assert await repository.listar_alertas(db_conn) == []

    monkeypatch.undo()
    # A leitura seguinte consegue abrir o alerta normalmente
    alerta = await repository.criar_alerta(db_conn, dados(maquina_id))
    assert alerta["manutencao_status"] == "pendente"


@pytest.mark.asyncio
async def test_erro_ao_atualizar_preserva_o_alerta(db_conn, monkeypatch):
    maquina_id, _ = await preparar(db_conn)
    alerta = await repository.criar_alerta(db_conn, dados(maquina_id))
    monkeypatch.setattr(
        repository,
        "_solicitar_manutencao",
        AsyncMock(side_effect=RuntimeError("falha simulada")),
    )

    resultado = await repository.atualizar_alerta(
        db_conn, alerta["id"], dados(maquina_id, mensagem="Não deve ser gravada")
    )

    assert resultado is None
    atual = await repository.obter_alerta(db_conn, alerta["id"])
    assert atual["mensagem"] == "Provável sobrecarga."


@pytest.mark.asyncio
async def test_rejeitar_nao_cria_ordem_e_nao_volta_a_pendente(db_conn):
    maquina_id, funcionario_id = await preparar(db_conn)
    alerta = await repository.criar_alerta(db_conn, dados(maquina_id))

    rejeitado = await repository.rejeitar_manutencao_alerta(
        db_conn, alerta["id"], funcionario_id, "Falso alarme"
    )
    atualizado = await repository.atualizar_alerta(
        db_conn, alerta["id"], dados(maquina_id)
    )

    assert rejeitado["analise_observacao"] == "Falso alarme"
    assert atualizado["manutencao_status"] == "rejeitada"
    assert await repository.listar_manutencoes_detalhadas(db_conn) == []
