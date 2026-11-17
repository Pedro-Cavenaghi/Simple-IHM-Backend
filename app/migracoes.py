"""Aplica as migrações SQL idempotentes de database/migrations na inicialização.

Cada arquivo usa CREATE ... IF NOT EXISTS, então rodar de novo não altera nada.
Assim, um deploy novo no Railway cria as tabelas que faltam sem passo manual.
"""

from pathlib import Path

import asyncpg

PASTA_MIGRACOES = Path(__file__).resolve().parent.parent / "database" / "migrations"


async def aplicar_migracoes(
    pool: asyncpg.Pool, pasta: Path = PASTA_MIGRACOES
) -> list[str]:
    aplicadas = []
    async with pool.acquire() as conn:
        for arquivo in sorted(pasta.glob("*.sql")):
            await conn.execute(arquivo.read_text(encoding="utf-8"))
            aplicadas.append(arquivo.name)
    return aplicadas
