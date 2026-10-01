import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Credenciais(BaseSettings):
    db_user: str = ""
    db_password: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_name: str = ""
    api_env: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


credenciais = Credenciais()

DATABASE_URL_RAILWAY = os.environ.get("DATABASE_URL")
