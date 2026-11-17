"""Grava o rótulo verdadeiro de cada leitura em CSV, para treinar e avaliar o ML.

O rótulo nunca vai no payload da API: uma ESP32 real não sabe que está com falha.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

COLUNAS = (
    "registrado_em_utc",
    "maquina_id",
    "tag_maquina",
    "status",
    "cenario",
    "parametros_alterados",
    "tensao_volt",
    "corrente_ampere",
    "potencia_watt",
    "vibracao_rms",
    "frequencia_hz",
    "resultado_envio",
)


class GravadorRotulos:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)

    def registrar(
        self,
        leitura: dict,
        tag_maquina: str,
        cenario: str,
        parametros_alterados: bool,
        resultado_envio: str,
        momento: datetime | None = None,
    ) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo_novo = not self.caminho.exists() or self.caminho.stat().st_size == 0

        linha = {
            "registrado_em_utc": (momento or datetime.now(timezone.utc)).isoformat(),
            "maquina_id": leitura["maquina_id"],
            "tag_maquina": tag_maquina,
            "status": leitura["status_atual"],
            "cenario": cenario,
            "parametros_alterados": int(parametros_alterados),
            "tensao_volt": leitura["tensao_volt"],
            "corrente_ampere": leitura["corrente_ampere"],
            "potencia_watt": leitura["potencia_watt"],
            "vibracao_rms": leitura["vibracao_rms"],
            "frequencia_hz": leitura["frequencia_hz"],
            "resultado_envio": resultado_envio,
        }

        with self.caminho.open("a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
            if arquivo_novo:
                escritor.writeheader()
            escritor.writerow(linha)
