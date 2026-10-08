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


@pytest.mark.asyncio
async def test_salvar_leitura(db_conn):
    maquina = await criar_maquina(db_conn)

    dados = {
        "maquina_id": maquina["id"],
        "status_atual": "Ativa",
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
    }

    sucesso = await repository.salvar_leitura(
        db_conn,
        dados,
    )

    assert sucesso is True

    quantidade_logs = await db_conn.fetchval(
        """
        SELECT COUNT(*)
        FROM logs_maquinas
        WHERE maquina_id = $1;
        """,
        maquina["id"],
    )

    assert quantidade_logs == 1

    status = await db_conn.fetchrow(
        """
        SELECT *
        FROM status_atual_maquinas
        WHERE maquina_id = $1;
        """,
        maquina["id"],
    )

    assert status is not None
    assert status["status_atual"] == "Ativa"
    assert status["tensao_volt"] == 220.0
    assert status["frequencia_hz"] == 60.0


@pytest.mark.asyncio
async def test_salvar_nova_leitura_atualiza_status(db_conn):
    maquina = await criar_maquina(db_conn)

    primeira_leitura = {
        "maquina_id": maquina["id"],
        "status_atual": "Ativa",
        "vibracao_rms": 1.0,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
    }

    segunda_leitura = {
        "maquina_id": maquina["id"],
        "status_atual": "Manutenção",
        "vibracao_rms": 3.5,
        "corrente_ampere": 8.0,
        "tensao_volt": 215.0,
        "potencia_watt": 1800.0,
        "frequencia_hz": 59.0,
    }

    await repository.salvar_leitura(
        db_conn,
        primeira_leitura,
    )

    await repository.salvar_leitura(
        db_conn,
        segunda_leitura,
    )

    quantidade_logs = await db_conn.fetchval(
        """
        SELECT COUNT(*)
        FROM logs_maquinas
        WHERE maquina_id = $1;
        """,
        maquina["id"],
    )

    assert quantidade_logs == 2

    quantidade_status = await db_conn.fetchval(
        """
        SELECT COUNT(*)
        FROM status_atual_maquinas
        WHERE maquina_id = $1;
        """,
        maquina["id"],
    )

    assert quantidade_status == 1

    status = await repository.obter_status_por_id(
        db_conn,
        maquina["id"],
    )

    assert status is not None
    assert status["status_atual"] == "Manutenção"
    assert status["vibracao_rms"] == 3.5
    assert status["tensao_volt"] == 215.0

@pytest.mark.asyncio
async def test_obter_status_atual(db_conn):
    maquina = await criar_maquina(db_conn)

    await repository.salvar_leitura(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "status_atual": "Ativa",
            "vibracao_rms": 1.5,
            "corrente_ampere": 10.0,
            "tensao_volt": 220.0,
            "potencia_watt": 2000.0,
            "frequencia_hz": 60.0,
        },
    )

    maquinas = await repository.obter_status_atual(db_conn)

    assert len(maquinas) == 1

    status = dict(maquinas[0])

    assert status["maquina_id"] == maquina["id"]
    assert status["tag_maquina"] == "INJ-01"
    assert status["nome_maquina"] == "Injetora 01"
    assert status["status_atual"] == "Ativa"


@pytest.mark.asyncio
async def test_obter_status_por_id_inexistente(db_conn):
    status = await repository.obter_status_por_id(
        db_conn,
        999,
    )

    assert status is None


@pytest.mark.asyncio
async def test_status_nao_exibe_maquina_removida(db_conn):
    maquina = await criar_maquina(db_conn)

    await repository.salvar_leitura(
        db_conn,
        {
            "maquina_id": maquina["id"],
            "status_atual": "Ativa",
            "vibracao_rms": 1.5,
            "corrente_ampere": 10.0,
            "tensao_volt": 220.0,
            "potencia_watt": 2000.0,
            "frequencia_hz": 60.0,
        },
    )

    await repository.soft_delete_maquina(
        db_conn,
        maquina["id"],
    )

    status = await repository.obter_status_por_id(
        db_conn,
        maquina["id"],
    )

    assert status is None

    maquinas = await repository.obter_status_atual(db_conn)

    assert maquinas == []


@pytest.mark.asyncio
async def test_salvar_leitura_maquina_inexistente(db_conn):
    dados = {
        "maquina_id": 999,
        "status_atual": "Ativa",
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
    }

    sucesso = await repository.salvar_leitura(
        db_conn,
        dados,
    )

    assert sucesso is False

    quantidade_logs = await db_conn.fetchval(
        "SELECT COUNT(*) FROM logs_maquinas;"
    )

    quantidade_status = await db_conn.fetchval(
        "SELECT COUNT(*) FROM status_atual_maquinas;"
    )

    assert quantidade_logs == 0
    assert quantidade_status == 0