
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from app import repository


def criar_conexao_mock():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock()
    return conn


# ==========================================
# DESCOBERTA DO TURNO
# ==========================================


@pytest.mark.parametrize(
    ("horario", "turno_esperado"),
    [
        (time(6, 0), 1),
        (time(13, 59), 1),
        (time(14, 0), 2),
        (time(21, 59), 2),
        (time(22, 0), 3),
        (time(5, 59), 3),
    ],
)
def test_descobrir_turno_atual(monkeypatch, horario, turno_esperado):
    class DataHoraFalsa:
        @staticmethod
        def now():
            return SimpleNamespace(time=lambda: horario)

    monkeypatch.setattr(repository, "datetime", DataHoraFalsa)

    assert repository.descobrir_turno_atual() == turno_esperado


# ==========================================
# TELEMETRIA
# ==========================================


@pytest.mark.asyncio
async def test_salvar_leitura_trata_erro_na_transacao():
    conn = criar_conexao_mock()

    contexto = MagicMock()
    contexto.__aenter__ = AsyncMock(
        side_effect=Exception("Falha na transação")
    )
    contexto.__aexit__ = AsyncMock(return_value=False)

    conn.transaction.return_value = contexto

    dados = {
        "maquina_id": 1,
        "status_atual": "Normal",
        "vibracao_rms": 0.5,
        "corrente_ampere": 2.0,
        "tensao_volt": 220.0,
        "potencia_watt": 440.0,
    }

    resultado = await repository.salvar_leitura(conn, dados)

    assert resultado is False


@pytest.mark.asyncio
async def test_obter_status_atual_trata_erro():
    conn = criar_conexao_mock()
    conn.fetch.side_effect = Exception("Erro no banco")

    assert await repository.obter_status_atual(conn) == []


@pytest.mark.asyncio
async def test_obter_status_por_id_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = Exception("Erro no banco")

    resultado = await repository.obter_status_por_id(conn, 1)

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_historico_logs_trata_erro():
    conn = criar_conexao_mock()
    conn.fetch.side_effect = Exception("Erro no banco")

    resultado = await repository.buscar_historico_logs(
        conn, 1, "hoje", None, None
    )

    assert resultado == []


# ==========================================
# FUNCIONÁRIOS
# ==========================================


def dados_funcionario():
    return {
        "nome": "João Silva",
        "cargo": "Operador",
        "turno_trabalho": 1,
        "email": "joao@email.com",
        "senha_hash": "hash_teste",
    }


@pytest.mark.asyncio
async def test_cadastrar_funcionario_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchval.side_effect = Exception("Erro no banco")

    resultado = await repository.cadastrar_funcionario(
        conn, dados_funcionario()
    )

    assert resultado is None


@pytest.mark.asyncio
async def test_cadastrar_funcionario_repassa_violacao_unica():
    conn = criar_conexao_mock()
    conn.fetchval.side_effect = asyncpg.exceptions.UniqueViolationError(
        "Registro duplicado"
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repository.cadastrar_funcionario(conn, dados_funcionario())


@pytest.mark.asyncio
async def test_listar_funcionarios_ativos_trata_erro():
    conn = criar_conexao_mock()
    conn.fetch.side_effect = Exception("Erro no banco")

    assert await repository.listar_funcionarios_ativos(conn) == []


@pytest.mark.asyncio
async def test_soft_delete_funcionario_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.soft_delete_funcionario(conn, 1)

    assert resultado is False


@pytest.mark.asyncio
async def test_obter_funcionario_por_id_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = Exception("Erro no banco")

    resultado = await repository.obter_funcionario_por_id(conn, 1)

    assert resultado is None


@pytest.mark.asyncio
async def test_atualizar_funcionario_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.atualizar_funcionario(
        conn, 1, dados_funcionario()
    )

    assert resultado is False


@pytest.mark.asyncio
async def test_atualizar_funcionario_repassa_violacao_unica():
    conn = criar_conexao_mock()
    conn.execute.side_effect = asyncpg.exceptions.UniqueViolationError(
        "Email duplicado"
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repository.atualizar_funcionario(
            conn, 1, dados_funcionario()
        )


# ==========================================
# MÁQUINAS
# ==========================================


def dados_maquina():
    return {
        "tag_maquina": " maq-001 ",
        "nome_maquina": " Máquina de Teste ",
        "setor": "Produção",
    }


@pytest.mark.asyncio
async def test_cadastrar_maquina_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = Exception("Erro no banco")

    resultado = await repository.cadastrar_maquina(conn, dados_maquina())

    assert resultado is None


@pytest.mark.asyncio
async def test_cadastrar_maquina_repassa_violacao_unica():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = asyncpg.exceptions.UniqueViolationError(
        "Tag duplicada"
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repository.cadastrar_maquina(conn, dados_maquina())


@pytest.mark.asyncio
async def test_listar_maquinas_cadastradas_trata_erro():
    conn = criar_conexao_mock()
    conn.fetch.side_effect = Exception("Erro no banco")

    assert await repository.listar_maquinas_cadastradas(conn) == []


@pytest.mark.asyncio
async def test_obter_maquina_por_id_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = Exception("Erro no banco")

    resultado = await repository.obter_maquina_por_id(conn, 1)

    assert resultado is None


@pytest.mark.asyncio
async def test_atualizar_maquina_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.atualizar_maquina(
        conn, 1, dados_maquina()
    )

    assert resultado is False


@pytest.mark.asyncio
async def test_atualizar_maquina_repassa_violacao_unica():
    conn = criar_conexao_mock()
    conn.execute.side_effect = asyncpg.exceptions.UniqueViolationError(
        "Tag duplicada"
    )

    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await repository.atualizar_maquina(
            conn, 1, dados_maquina()
        )


@pytest.mark.asyncio
async def test_soft_delete_maquina_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.soft_delete_maquina(conn, 1)

    assert resultado is False


# ==========================================
# MANUTENÇÕES
# ==========================================


def dados_manutencao():
    return {
        "maquina_id": 1,
        "descricao_servico": " Revisão preventiva ",
        "data_agendada": "2026-12-10",
        "tipo_manutencao": "PREVENTIVA",
    }


@pytest.mark.asyncio
async def test_agendar_manutencao_com_maquina_inexistente():
    conn = criar_conexao_mock()
    conn.fetchval.return_value = None

    resultado = await repository.agendar_manutencao(
        conn, dados_manutencao()
    )

    assert resultado is None
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_agendar_manutencao_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchval.side_effect = Exception("Erro no banco")

    resultado = await repository.agendar_manutencao(
        conn, dados_manutencao()
    )

    assert resultado is None


@pytest.mark.asyncio
async def test_listar_manutencoes_detalhadas_trata_erro():
    conn = criar_conexao_mock()
    conn.fetch.side_effect = Exception("Erro no banco")

    assert await repository.listar_manutencoes_detalhadas(conn) == []


@pytest.mark.asyncio
async def test_obter_manutencao_por_id_trata_erro():
    conn = criar_conexao_mock()
    conn.fetchrow.side_effect = Exception("Erro no banco")

    resultado = await repository.obter_manutencao_por_id(conn, 1)

    assert resultado is None


@pytest.mark.asyncio
async def test_atualizar_dados_manutencao_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.atualizar_dados_manutencao(
        conn, 1, dados_manutencao()
    )

    assert resultado is False


@pytest.mark.asyncio
async def test_concluir_ordem_manutencao_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.concluir_ordem_manutencao(conn, 1, 1)

    assert resultado is False


@pytest.mark.asyncio
async def test_soft_delete_manutencao_trata_erro():
    conn = criar_conexao_mock()
    conn.execute.side_effect = Exception("Erro no banco")

    resultado = await repository.soft_delete_manutencao(conn, 1)

    assert resultado is False
