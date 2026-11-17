import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Destino da telemetria (a API do Simple IHM)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

# Mesma chave configurada no backend (app/auth.py). O padrão só serve para dev local.
API_KEY = os.getenv("API_KEY", "chave_interna_simple_ihm_2026")

# Cadência de envio, igual à de uma ESP32 real
INTERVALO_ENVIO_S = float(os.getenv("INTERVALO_ENVIO_S", "2"))

# Sobe com todas as máquinas pausadas: reinícios e deploys nunca religam o envio sozinhos
INICIAR_PAUSADO = os.getenv("INICIAR_PAUSADO", "false").strip().lower() in {
    "1",
    "true",
    "sim",
    "yes",
}

# De quanto em quanto tempo a lista de máquinas e as manutenções são recarregadas
INTERVALO_SINCRONIZACAO_S = float(os.getenv("INTERVALO_SINCRONIZACAO_S", "15"))

# CSV com o rótulo verdadeiro de cada leitura (dataset para o ML)
ARQUIVO_ROTULOS = Path(
    os.getenv("ARQUIVO_ROTULOS", str(Path(__file__).parent / "dados" / "rotulos.csv"))
)

# Senha do painel. Vazia = painel aberto (uso local). Defina em produção.
PAINEL_SENHA = os.getenv("PAINEL_SENHA", "")

# Assina o cookie de sessão do login. Sem valor fixo, as sessões caem a cada restart.
STORAGE_SECRET = os.getenv("STORAGE_SECRET") or secrets.token_urlsafe(32)

# O Railway injeta PORT; localmente o painel sobe na 8081 (a API usa a 8000)
PORTA = int(os.getenv("PORT", "8081"))
