import asyncpg
import os # noqa: F401
from .dbconfig import credenciais, DATABASE_URL_RAILWAY

if DATABASE_URL_RAILWAY:
    if DATABASE_URL_RAILWAY.startswith("postgres://"):
        DB_URI = DATABASE_URL_RAILWAY.replace("postgres://", "postgresql://", 1)
    else:
        DB_URI = DATABASE_URL_RAILWAY
else:
    DB_URI = f"postgresql://{credenciais.db_user}:{credenciais.db_password}@{credenciais.db_host}:{credenciais.db_port}/{credenciais.db_name}"


class Database:
    pool = None

    @classmethod
    def get_pool(cls):
        if cls.pool is None:
            raise RuntimeError("O Pool de conexões não foi inicializado!")
        return cls.pool

    @classmethod
    async def connect(cls):
        print("--- Inicializando Pool de Conexões Otimizado (asyncpg) ---")
        cls.pool = await asyncpg.create_pool(DB_URI, min_size=2, max_size=10)

    @classmethod
    async def disconnect(cls):
        if cls.pool:
            print("--- Fechando Pool de Conexões com Segurança ---")
            await cls.pool.close()


async def get_db():
    pool = Database.get_pool()
    async with pool.acquire() as connection:
        yield connection
