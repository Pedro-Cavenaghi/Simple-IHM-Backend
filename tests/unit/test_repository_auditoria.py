
from unittest.mock import AsyncMock

import pytest

import app.repository as repository


@pytest.mark.asyncio
async def test_registrar_auditoria_retorna_false_quando_banco_falha():
    conn = AsyncMock()
    conn.execute.side_effect = Exception("Erro simulado no banco")

    resultado = await repository.registrar_auditoria(
        conn,
        1,
        "CRIAR",
        "MAQUINA",
        10,
        "Teste de falha",
    )

    assert resultado is False
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_listar_logs_auditoria_retorna_lista_vazia_quando_banco_falha():
    conn = AsyncMock()
    conn.fetch.side_effect = Exception("Erro simulado no banco")

    resultado = await repository.listar_logs_auditoria(conn)

    assert resultado == []
    conn.fetch.assert_awaited_once()
