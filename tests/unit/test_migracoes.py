from unittest.mock import AsyncMock, MagicMock

import pytest

from app.migracoes import PASTA_MIGRACOES, aplicar_migracoes


def criar_pool():
    conn = MagicMock()
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_aplica_arquivos_em_ordem(tmp_path):
    (tmp_path / "002_b.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "leia-me.txt").write_text("ignorar", encoding="utf-8")
    pool, conn = criar_pool()

    aplicadas = await aplicar_migracoes(pool, tmp_path)

    assert aplicadas == ["001_a.sql", "002_b.sql"]
    assert [c.args[0] for c in conn.execute.await_args_list] == [
        "SELECT 1;",
        "SELECT 2;",
    ]


def test_migracoes_do_projeto_sao_idempotentes():
    """Rodam a cada inicialização da API, então não podem falhar na 2ª vez."""
    for arquivo in PASTA_MIGRACOES.glob("*.sql"):
        sql = arquivo.read_text(encoding="utf-8").upper()
        assert sql.count("CREATE TABLE IF NOT EXISTS") == sql.count("CREATE TABLE")
        assert sql.count("INDEX IF NOT EXISTS") == sql.count(" INDEX ")
