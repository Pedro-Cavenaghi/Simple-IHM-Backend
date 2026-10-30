import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app import repository
from app.database import get_db
from app.models import FuncionarioResponse

# Carrega as variáveis do arquivo .env logo após os imports
load_dotenv()

# Configurações de Segurança
SECRET_KEY = os.getenv("SECRET_KEY", "sua_chave_secreta_super_segura_aqui")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY", "chave_interna_simple_ihm_2026")

security_bearer = HTTPBearer()
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


# ------------------------------------------------------------------
# 1. VALIDAÇÃO DE API KEY (ESP32 / MÁQUINA)
# ------------------------------------------------------------------


async def verificar_api_key(api_key: Optional[str] = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou ausente.",
        )
    return api_key


# ------------------------------------------------------------------
# 2. CRIAÇÃO E VALIDAÇÃO DE TOKEN JWT
# ------------------------------------------------------------------


def criar_token_acesso(dados: dict) -> str:
    dados_para_codificar = dados.copy()
    expiracao = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    dados_para_codificar.update({"exp": expiracao})
    return jwt.encode(dados_para_codificar, SECRET_KEY, algorithm=ALGORITHM)


def validar_token_jwt_simples(token: str) -> dict | None:
    """Valida e decodifica o JWT vindo do Handshake do WebSocket sem ir ao banco."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def obter_usuario_atual(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    conn=Depends(get_db),
) -> FuncionarioResponse:
    token = credentials.credentials
    credenciais_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais de acesso.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id_str: str = payload.get("sub")
        if usuario_id_str is None:
            raise credenciais_exception
        usuario_id = int(usuario_id_str)
    except (JWTError, ValueError):
        raise credenciais_exception

    usuario_dict = await repository.obter_funcionario_por_id(conn, usuario_id)
    if usuario_dict is None:
        raise credenciais_exception

    return FuncionarioResponse(**usuario_dict)


# ------------------------------------------------------------------
# 3. CONTROLE DE PERMISSÕES POR ROLE (RBAC)
# ------------------------------------------------------------------


class PermissaoRequerida:
    def __init__(self, perfis_permitidos: list[str]):
        self.perfis_permitidos = perfis_permitidos

    def __call__(
        self, usuario_atual: FuncionarioResponse = Depends(obter_usuario_atual)
    ):
        if usuario_atual.perfil not in self.perfis_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Acesso negado. Perfil '{usuario_atual.perfil}' não possui"
                    " permissão para esta operação."
                ),
            )
        return usuario_atual
