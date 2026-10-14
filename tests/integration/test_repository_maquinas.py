import pytest
import asyncpg

import app.repository as repository


@pytest.mark.asyncio
async def test_cadastrar_e_obter_maquina(db_conn):
    dados = {
        "tag_maquina": "inj-01",
        "nome_maquina": "Injetora 01",
        "setor": "Produção",
    }

    maquina_criada = await repository.cadastrar_maquina(
        db_conn,
        dados,
    )

    assert maquina_criada is not None
    assert maquina_criada["id"] == 1
    assert maquina_criada["tag_maquina"] == "INJ-01"
    assert maquina_criada["nome_maquina"] == "Injetora 01"
    assert maquina_criada["setor"] == "Produção"

    maquina_buscada = await repository.obter_maquina_por_id(
        db_conn,
        maquina_criada["id"],
    )

    assert maquina_buscada is not None
    assert maquina_buscada["id"] == maquina_criada["id"]
    assert maquina_buscada["tag_maquina"] == "INJ-01"
    assert maquina_buscada["nome_maquina"] == "Injetora 01"
    assert maquina_buscada["setor"] == "Produção"

@pytest.mark.asyncio
async def test_listar_maquinas(db_conn):
    await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "mtr-02",
            "nome_maquina": "Motor 02",
            "setor": "Montagem",
        },
    )

    await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "inj-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    maquinas = await repository.listar_maquinas_cadastradas(db_conn)

    assert len(maquinas) == 2
    assert maquinas[0]["tag_maquina"] == "INJ-01"
    assert maquinas[1]["tag_maquina"] == "MTR-02"


@pytest.mark.asyncio
async def test_atualizar_maquina(db_conn):
    maquina = await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "inj-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    sucesso = await repository.atualizar_maquina(
        db_conn,
        maquina["id"],
        {
            "tag_maquina": "inj-02",
            "nome_maquina": "Injetora Atualizada",
            "setor": "Usinagem",
        },
    )

    assert sucesso is True

    maquina_atualizada = await repository.obter_maquina_por_id(
        db_conn,
        maquina["id"],
    )

    assert maquina_atualizada["tag_maquina"] == "INJ-02"
    assert maquina_atualizada["nome_maquina"] == "Injetora Atualizada"
    assert maquina_atualizada["setor"] == "Usinagem"


@pytest.mark.asyncio
async def test_atualizar_maquina_inexistente(db_conn):
    sucesso = await repository.atualizar_maquina(
        db_conn,
        999,
        {
            "tag_maquina": "INJ-99",
            "nome_maquina": "Máquina Inexistente",
            "setor": "Produção",
        },
    )

    assert sucesso is False


@pytest.mark.asyncio
async def test_soft_delete_maquina(db_conn):
    maquina = await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "inj-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    sucesso = await repository.soft_delete_maquina(
        db_conn,
        maquina["id"],
    )

    assert sucesso is True

    maquina_buscada = await repository.obter_maquina_por_id(
        db_conn,
        maquina["id"],
    )

    assert maquina_buscada is None


@pytest.mark.asyncio
async def test_soft_delete_maquina_ja_removida(db_conn):
    maquina = await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "inj-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    await repository.soft_delete_maquina(
        db_conn,
        maquina["id"],
    )

    segunda_tentativa = await repository.soft_delete_maquina(
        db_conn,
        maquina["id"],
    )

    assert segunda_tentativa is False


@pytest.mark.asyncio
async def test_nao_permite_tag_duplicada(db_conn):
    await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "setor": "Produção",
        },
    )

    with pytest.raises(asyncpg.UniqueViolationError):
        await repository.cadastrar_maquina(
            db_conn,
            {
                "tag_maquina": "inj-01",
                "nome_maquina": "Outra Injetora",
                "setor": "Montagem",
            },
        )


@pytest.mark.asyncio
async def test_permite_reutilizar_tag_apos_soft_delete(db_conn):
    primeira = await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora Antiga",
            "setor": "Produção",
        },
    )

    await repository.soft_delete_maquina(
        db_conn,
        primeira["id"],
    )

    nova = await repository.cadastrar_maquina(
        db_conn,
        {
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora Nova",
            "setor": "Produção",
        },
    )

    assert nova is not None
    assert nova["tag_maquina"] == "INJ-01"
    assert nova["id"] != primeira["id"]