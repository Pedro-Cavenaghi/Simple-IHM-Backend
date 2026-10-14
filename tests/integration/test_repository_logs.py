from datetime import datetime, time, timedelta

import pytest

import app.repository as repository


async def criar_maquina(db_conn, tag="INJ-01", nome="Injetora 01"):
    return await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": tag,
            "nome_maquina": nome,
            "setor": "Produção",
        },
    )


async def inserir_log(
    db_conn,
    maquina_id,
    horario,
    status="Ativa",
):
    await db_conn.execute(
        """
        INSERT INTO logs_maquinas (
            horario_do_log,
            maquina_id,
            turno,
            vibracao_rms,
            corrente_ampere,
            tensao_volt,
            potencia_watt,
            status_no_momento,
            frequencia_hz
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
        """,
        horario,
        maquina_id,
        1,
        1.5,
        10.0,
        220.0,
        2000.0,
        status,
        60.0,
    )


@pytest.mark.asyncio
async def test_buscar_logs_de_hoje(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(10, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=2), time(10, 0)),
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="hoje",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )

    assert len(logs) == 1
    assert logs[0]["maquina_id"] == maquina["id"]


@pytest.mark.asyncio
async def test_buscar_logs_da_semana(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=3), time(10, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=10), time(10, 0)),
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="semana",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )

    assert len(logs) == 1


@pytest.mark.asyncio
async def test_buscar_logs_do_mes(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=15), time(10, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=40), time(10, 0)),
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="mes",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )

    assert len(logs) == 1


@pytest.mark.asyncio
async def test_filtrar_logs_por_maquina(db_conn):
    maquina_1 = await criar_maquina(
        db_conn,
        tag="INJ-01",
        nome="Injetora 01",
    )

    maquina_2 = await criar_maquina(
        db_conn,
        tag="MTR-02",
        nome="Motor 02",
    )

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    horario = datetime.combine(hoje, time(10, 0))

    await inserir_log(
        db_conn,
        maquina_1["id"],
        horario,
    )

    await inserir_log(
        db_conn,
        maquina_2["id"],
        horario,
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=maquina_1["id"],
        periodo="hoje",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )

    assert len(logs) == 1
    assert logs[0]["maquina_id"] == maquina_1["id"]


@pytest.mark.asyncio
async def test_buscar_logs_periodo_customizado(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    data_inicio = hoje - timedelta(days=10)
    data_fim = hoje - timedelta(days=5)

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=7), time(10, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje - timedelta(days=2), time(10, 0)),
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="customizado",
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=500,
    )

    assert len(logs) == 1


@pytest.mark.asyncio
async def test_logs_ordenados_do_mais_recente(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(8, 0)),
        status="Ativa",
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(10, 0)),
        status="Inativa",
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(12, 0)),
        status="Manutenção",
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="hoje",
        data_inicio=None,
        data_fim=None,
        limite=500,
    )

    assert len(logs) == 3

    assert logs[0]["status_no_momento"] == "Manutenção"
    assert logs[1]["status_no_momento"] == "Inativa"
    assert logs[2]["status_no_momento"] == "Ativa"


@pytest.mark.asyncio
async def test_limite_de_logs(db_conn):
    maquina = await criar_maquina(db_conn)

    hoje = await db_conn.fetchval("SELECT CURRENT_DATE")

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(8, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(10, 0)),
    )

    await inserir_log(
        db_conn,
        maquina["id"],
        datetime.combine(hoje, time(12, 0)),
    )

    logs = await repository.buscar_historico_logs(
        conn=db_conn,
        maquina_id=None,
        periodo="hoje",
        data_inicio=None,
        data_fim=None,
        limite=2,
    )

    assert len(logs) == 2