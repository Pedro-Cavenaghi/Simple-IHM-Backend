from datetime import date, timedelta

import pytest

import app.repository as repository


async def criar_maquina(db_conn, tag: str, nome: str):
    return await repository.cadastrar_maquina(
        db_conn,
        {"tag_maquina": tag, "nome_maquina": nome, "setor": "Produção"},
    )


async def agendar(db_conn, maquina_id: int, data_agendada: date):
    return await repository.agendar_manutencao(
        db_conn,
        {
            "maquina_id": maquina_id,
            "descricao_servico": "Troca de rolamento",
            "data_agendada": data_agendada,
            "tipo_manutencao": "Preditiva",
        },
    )


@pytest.mark.asyncio
async def test_maquina_sem_ordens_nao_esta_em_manutencao(db_conn):
    await criar_maquina(db_conn, "CNC-01", "Torno CNC")

    maquinas = await repository.listar_maquinas_para_dispositivos(db_conn)

    assert len(maquinas) == 1
    assert maquinas[0]["tag_maquina"] == "CNC-01"
    assert maquinas[0]["em_manutencao"] is False


@pytest.mark.asyncio
async def test_ordem_aberta_para_hoje_coloca_maquina_em_manutencao(db_conn):
    maquina = await criar_maquina(db_conn, "CNC-01", "Torno CNC")
    await agendar(db_conn, maquina["id"], date.today())

    maquinas = await repository.listar_maquinas_para_dispositivos(db_conn)

    assert maquinas[0]["em_manutencao"] is True


@pytest.mark.asyncio
async def test_ordem_futura_nao_coloca_maquina_em_manutencao(db_conn):
    maquina = await criar_maquina(db_conn, "CNC-01", "Torno CNC")
    await agendar(db_conn, maquina["id"], date.today() + timedelta(days=7))

    maquinas = await repository.listar_maquinas_para_dispositivos(db_conn)

    assert maquinas[0]["em_manutencao"] is False


@pytest.mark.asyncio
async def test_ordem_concluida_libera_a_maquina(db_conn):
    maquina = await criar_maquina(db_conn, "CNC-01", "Torno CNC")
    funcionario_id = await repository.cadastrar_funcionario(
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
    ordem = await agendar(db_conn, maquina["id"], date.today())
    await repository.concluir_ordem_manutencao(db_conn, ordem["id"], funcionario_id)

    maquinas = await repository.listar_maquinas_para_dispositivos(db_conn)

    assert maquinas[0]["em_manutencao"] is False


@pytest.mark.asyncio
async def test_maquinas_desativadas_nao_sao_listadas(db_conn):
    ativa = await criar_maquina(db_conn, "CNC-01", "Torno CNC")
    desativada = await criar_maquina(db_conn, "INJ-01", "Injetora 01")
    await repository.soft_delete_maquina(db_conn, desativada["id"])

    maquinas = await repository.listar_maquinas_para_dispositivos(db_conn)

    assert [m["id"] for m in maquinas] == [ativa["id"]]
