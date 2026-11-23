import json

import pytest

import app.repository as repository


async def criar_maquina(db_conn):
    return await repository.cadastrar_maquina(
        db_conn,
        {"tag_maquina": "INJ-01", "nome_maquina": "Injetora 01", "setor": "Produção"},
    )


def dados_alerta(maquina_id, **extra):
    return {
        "maquina_id": maquina_id,
        "diagnostico": "sobrecarga",
        "confianca": 0.9,
        "pontuacao": 0.4,
        "severidade": "alta",
        "mensagem": "Provável sobrecarga (confiança de 90%).",
        **extra,
    }


@pytest.mark.asyncio
async def test_ciclo_de_vida_do_alerta(db_conn):
    maquina = await criar_maquina(db_conn)

    criado = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))
    assert criado["tag_maquina"] == "INJ-01"
    assert criado["encerrado_em"] is None

    atualizado = await repository.atualizar_alerta(
        db_conn,
        criado["id"],
        dados_alerta(
            maquina["id"], diagnostico="desgaste_rolamento", minutos_ate_limite=3.5
        ),
    )
    assert atualizado["diagnostico"] == "desgaste_rolamento"
    assert atualizado["minutos_ate_limite"] == pytest.approx(3.5)

    encerrado = await repository.encerrar_alerta(db_conn, criado["id"])
    assert encerrado["encerrado_em"] is not None
    # Alerta encerrado não volta a ser alterado
    assert await repository.encerrar_alerta(db_conn, criado["id"]) is None
    assert (
        await repository.atualizar_alerta(
            db_conn, criado["id"], dados_alerta(maquina["id"])
        )
        is None
    )


@pytest.mark.asyncio
async def test_listar_alertas_filtra_abertos_e_maquina(db_conn):
    maquina = await criar_maquina(db_conn)
    antigo = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))
    await repository.encerrar_alerta(db_conn, antigo["id"])
    aberto = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))

    todos = await repository.listar_alertas(db_conn)
    abertos = await repository.listar_alertas(db_conn, apenas_abertos=True)
    de_outra = await repository.listar_alertas(db_conn, maquina_id=maquina["id"] + 1)

    assert [a["id"] for a in todos] == [aberto["id"], antigo["id"]]
    assert [a["id"] for a in abertos] == [aberto["id"]]
    assert de_outra == []


@pytest.mark.asyncio
async def test_um_unico_alerta_aberto_por_maquina(db_conn):
    maquina = await criar_maquina(db_conn)
    await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))

    segundo = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))

    assert segundo is None


@pytest.mark.asyncio
async def test_reconhecer_alerta_uma_vez(db_conn):
    maquina = await criar_maquina(db_conn)
    funcionario_id = await repository.cadastrar_funcionario(
        db_conn,
        {
            "nome": "Ana Operadora",
            "cargo": "Operadora",
            "turno_trabalho": 1,
            "email": "ana@email.com",
            "senha_hash": "hash",
            "ativo": True,
            "perfil": "OPERADOR",
        },
    )
    alerta = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))

    reconhecido = await repository.reconhecer_alerta(
        db_conn, alerta["id"], funcionario_id
    )

    assert reconhecido["reconhecido_por_nome"] == "Ana Operadora"
    assert (
        await repository.reconhecer_alerta(db_conn, alerta["id"], funcionario_id)
        is None
    )


@pytest.mark.asyncio
async def test_linha_de_base_e_gravada_no_alerta(db_conn):
    maquina = await criar_maquina(db_conn)
    base = {"vibracao_rms": 2.0, "tensao_volt": 220.0}

    alerta = await repository.criar_alerta(
        db_conn, dados_alerta(maquina["id"], linha_de_base=base)
    )

    assert json.loads(alerta["linha_de_base"]) == base


@pytest.mark.asyncio
async def test_leituras_recentes_ignoram_periodo_do_alerta(db_conn):
    maquina = await criar_maquina(db_conn)

    async def gravar(vibracao, ha_minutos):
        await db_conn.execute(
            """
            INSERT INTO logs_maquinas
            (maquina_id, status_no_momento, vibracao_rms, corrente_ampere,
             tensao_volt, potencia_watt, frequencia_hz, horario_do_log)
            VALUES ($1, 'Ativa', $2, 10, 220, 2000, 60,
                    NOW() - make_interval(mins => $3));
            """,
            maquina["id"],
            vibracao,
            ha_minutos,
        )

    await gravar(1.0, 30)
    await gravar(9.0, 15)
    await gravar(2.0, 5)
    alerta = await repository.criar_alerta(db_conn, dados_alerta(maquina["id"]))
    await db_conn.execute(
        """
        UPDATE alertas
        SET criado_em = NOW() - interval '20 minutes',
            encerrado_em = NOW() - interval '10 minutes'
        WHERE id = $1;
        """,
        alerta["id"],
    )

    leituras = await repository.buscar_leituras_recentes(
        db_conn, maquina["id"], limite=10
    )

    assert [leitura["vibracao_rms"] for leitura in leituras] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_buscar_leituras_recentes_so_ativas_em_ordem(db_conn):
    maquina = await criar_maquina(db_conn)
    for i, status in enumerate(["Ativa", "Ativa", "Desligada", "Ativa"]):
        await repository.salvar_leitura(
            db_conn,
            {
                "maquina_id": maquina["id"],
                "status_atual": status,
                "vibracao_rms": float(i),
                "corrente_ampere": 10.0,
                "tensao_volt": 220.0,
                "potencia_watt": 2000.0,
                "frequencia_hz": 60.0,
            },
        )

    leituras = await repository.buscar_leituras_recentes(
        db_conn, maquina["id"], limite=2
    )

    assert [leitura["vibracao_rms"] for leitura in leituras] == [1.0, 3.0]
