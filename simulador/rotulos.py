"""Grava o rótulo verdadeiro de cada leitura em CSV, para treinar e avaliar o ML.

O rótulo nunca vai no payload da API: uma ESP32 real não sabe que está com falha.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

COLUNAS = (
    "registrado_em_utc",
    "sessao",  # separa treino e teste por sessão de coleta, não por linha
    "maquina_id",
    "tag_maquina",
    "status",
    "cenario",  # rótulo verdadeiro: normal, manutencao ou a chave da falha
    "intensidade",  # força da falha (0 quando normal)
    "cenario_progresso",  # 0 a 1: quanto da falha já passou (antecedência da detecção)
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
        self._arquivo: TextIO | None = None
        self._escritor: csv.DictWriter | None = None

    def _arquivar_formato_antigo(self) -> None:
        """Renomeia um CSV de versão anterior, para não misturar colunas diferentes."""
        with self.caminho.open(encoding="utf-8", newline="") as arquivo:
            cabecalho = next(csv.reader(arquivo), None)
        if cabecalho and tuple(cabecalho) != COLUNAS:
            sufixo = datetime.now().strftime("%Y%m%d-%H%M%S")
            antigo = self.caminho.with_name(
                f"{self.caminho.stem}-antigo-{sufixo}{self.caminho.suffix}"
            )
            self.caminho.rename(antigo)

    def _abrir(self) -> csv.DictWriter:
        if self._escritor is None:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            if self.caminho.exists() and self.caminho.stat().st_size > 0:
                self._arquivar_formato_antigo()
            novo = not self.caminho.exists() or self.caminho.stat().st_size == 0
            self._arquivo = self.caminho.open("a", newline="", encoding="utf-8")
            self._escritor = csv.DictWriter(self._arquivo, fieldnames=COLUNAS)
            if novo:
                self._escritor.writeheader()
        return self._escritor

    def registrar(
        self,
        leitura: dict,
        tag_maquina: str,
        cenario: str,
        parametros_alterados: bool,
        resultado_envio: str,
        momento: datetime | None = None,
        sessao: str = "manual",
        intensidade: float = 0.0,
        cenario_progresso: float = 0.0,
    ) -> None:
        escritor = self._abrir()
        escritor.writerow(
            {
                "registrado_em_utc": (
                    momento or datetime.now(timezone.utc)
                ).isoformat(),
                "sessao": sessao,
                "maquina_id": leitura["maquina_id"],
                "tag_maquina": tag_maquina,
                "status": leitura["status_atual"],
                "cenario": cenario,
                "intensidade": round(intensidade, 3),
                "cenario_progresso": round(cenario_progresso, 4),
                "parametros_alterados": int(parametros_alterados),
                "tensao_volt": leitura["tensao_volt"],
                "corrente_ampere": leitura["corrente_ampere"],
                "potencia_watt": leitura["potencia_watt"],
                "vibracao_rms": leitura["vibracao_rms"],
                "frequencia_hz": leitura["frequencia_hz"],
                "resultado_envio": resultado_envio,
            }
        )
        # Garante que o CSV baixado pelo painel está sempre completo
        self._arquivo.flush()

    def fechar(self) -> None:
        if self._arquivo:
            self._arquivo.close()
        self._arquivo = None
        self._escritor = None
