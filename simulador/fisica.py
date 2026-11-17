"""Modelo físico simplificado das máquinas: ruído, potência e cenários de falha.

Este módulo não depende da interface nem da rede, para poder ser testado isoladamente.
"""

import math
import random
from dataclasses import dataclass, replace

# Limites aceitos pela API (app/models.py -> LeituraSensor)
LIMITE_TENSAO_V = 250.0
LIMITE_FREQUENCIA_HZ = 100.0

STATUS_OPERACAO = ("Ativa", "Inativa", "Desligada")
STATUS_MANUTENCAO = "Manutenção"


@dataclass
class Parametros:
    """Valores base de uma máquina, controlados pelos sliders do painel.

    A potência não é um parâmetro: ela é sempre calculada (P = V x I x FP),
    para que o dataset nunca contenha combinações fisicamente impossíveis.
    """

    tensao_volt: float = 220.0
    corrente_ampere: float = 15.0
    fator_potencia: float = 0.85
    vibracao_rms: float = 1.5
    frequencia_hz: float = 60.0

    @property
    def potencia_watt(self) -> float:
        return calcular_potencia(
            self.tensao_volt, self.corrente_ampere, self.fator_potencia
        )


# Perfis nominais por tipo de máquina, identificado pelo prefixo da tag (ex.: CNC-01)
PERFIS_POR_PREFIXO: dict[str, Parametros] = {
    "CNC": Parametros(corrente_ampere=15.5, vibracao_rms=2.1, fator_potencia=0.85),
    "INJ": Parametros(corrente_ampere=32.0, vibracao_rms=5.8, fator_potencia=0.82),
    "PRE": Parametros(corrente_ampere=8.0, vibracao_rms=0.4, fator_potencia=0.88),
}


def perfil_padrao(tag_maquina: str) -> Parametros:
    prefixo = tag_maquina.split("-")[0].upper()
    return replace(PERFIS_POR_PREFIXO.get(prefixo, Parametros()))


def calcular_potencia(tensao: float, corrente: float, fator_potencia: float) -> float:
    return max(0.0, tensao * corrente * fator_potencia)


# ==========================================
# CENÁRIOS DE FALHA
# ==========================================


def envelope(t: float, duracao: float, rampa: float) -> float:
    """Intensidade de 0 a 1 que sobe em `rampa` segundos, se mantém e desce no fim."""
    if t <= 0 or t >= duracao:
        return 0.0
    if rampa <= 0:
        return 1.0
    return max(0.0, min(1.0, t / rampa, (duracao - t) / rampa))


@dataclass(frozen=True)
class Cenario:
    chave: str
    nome: str
    descricao: str
    icone: str
    duracao_s: float  # duração padrão, usada pelos botões do painel

    def aplicar(
        self,
        p: Parametros,
        t: float,
        duracao_s: float | None = None,
        intensidade: float = 1.0,
    ) -> Parametros:
        """Retorna os parâmetros alterados pela falha, `t` segundos após o início.

        `intensidade` escala o tamanho do efeito (1.0 = efeito padrão) e
        `duracao_s` permite falhas mais rápidas ou mais lentas que o padrão.
        """
        duracao = duracao_s if duracao_s is not None else self.duracao_s
        return _EFEITOS[self.chave](p, t, duracao, intensidade)


def _desgaste_rolamento(
    p: Parametros, t: float, duracao: float, k: float
) -> Parametros:
    # Deriva lenta e acelerada: o caso clássico que a manutenção preditiva deve detectar cedo
    progresso = min(1.0, max(0.0, t / duracao))
    return replace(
        p,
        vibracao_rms=p.vibracao_rms * (1 + 2.5 * k * progresso**1.5),
        corrente_ampere=p.corrente_ampere * (1 + 0.10 * k * progresso),
    )


def _sobrecarga(p: Parametros, t: float, duracao: float, k: float) -> Parametros:
    intensidade = k * envelope(t, duracao, rampa=3)
    return replace(
        p,
        corrente_ampere=p.corrente_ampere * (1 + 0.40 * intensidade),
        tensao_volt=p.tensao_volt * (1 - 0.03 * intensidade),
        vibracao_rms=p.vibracao_rms * (1 + 0.30 * intensidade),
    )


def _queda_tensao(p: Parametros, t: float, duracao: float, k: float) -> Parametros:
    intensidade = envelope(t, duracao, rampa=2)
    queda = 30.0 * k  # 220 V -> 190 V com intensidade 1
    return replace(
        p,
        tensao_volt=p.tensao_volt - queda * intensidade,
        # O motor puxa mais corrente para manter a potência mecânica
        corrente_ampere=p.corrente_ampere * (1 + 0.12 * k * intensidade),
    )


def _desbalanceamento(p: Parametros, t: float, duracao: float, k: float) -> Parametros:
    intensidade = k * envelope(t, duracao, rampa=10)
    oscilacao = 0.6 + 0.6 * math.sin(2 * math.pi * t / 6)
    return replace(
        p,
        vibracao_rms=p.vibracao_rms * (1 + intensidade * oscilacao),
        frequencia_hz=p.frequencia_hz
        + 0.5 * intensidade * math.sin(2 * math.pi * t / 6),
    )


_EFEITOS = {
    "desgaste_rolamento": _desgaste_rolamento,
    "sobrecarga": _sobrecarga,
    "queda_tensao": _queda_tensao,
    "desbalanceamento": _desbalanceamento,
}

CENARIOS: dict[str, Cenario] = {
    c.chave: c
    for c in (
        Cenario(
            "desgaste_rolamento",
            "Desgaste de rolamento",
            "Vibração sobe aos poucos por 5 min",
            "settings",
            300,
        ),
        Cenario(
            "sobrecarga",
            "Sobrecarga",
            "Corrente +40% por 30 s",
            "bolt",
            30,
        ),
        Cenario(
            "queda_tensao",
            "Queda de tensão",
            "Tensão cai para ~190 V por 45 s",
            "trending_down",
            45,
        ),
        Cenario(
            "desbalanceamento",
            "Desbalanceamento",
            "Vibração oscilante por 2 min",
            "cyclone",
            120,
        ),
    )
}


# ==========================================
# GERAÇÃO DA LEITURA
# ==========================================


def _com_ruido(rng: random.Random, valor: float, desvio_relativo: float) -> float:
    return rng.gauss(valor, abs(valor) * desvio_relativo)


def gerar_leitura(
    maquina_id: int,
    parametros: Parametros,
    status: str,
    ruido: bool = True,
    rng: random.Random | None = None,
) -> dict:
    """Monta o payload de POST /enviar-dados a partir dos parâmetros e do status."""
    rng = rng or random.Random()
    p = parametros

    def r(valor: float, desvio: float) -> float:
        return _com_ruido(rng, valor, desvio) if ruido else valor

    if status in (STATUS_MANUTENCAO, "Desligada"):
        # Motor parado, mas a rede elétrica continua energizada
        tensao = r(p.tensao_volt, 0.002)
        corrente = vibracao = frequencia = 0.0
        fator = p.fator_potencia
    elif status == "Inativa":
        # Ligada em vazio: corrente e vibração residuais
        tensao = r(p.tensao_volt, 0.005)
        corrente = r(0.5, 0.1)
        vibracao = r(0.1, 0.2)
        frequencia = r(p.frequencia_hz, 0.001)
        fator = 0.9
    else:
        tensao = r(p.tensao_volt, 0.005)
        corrente = r(p.corrente_ampere, 0.03)
        vibracao = r(p.vibracao_rms, 0.08)
        frequencia = r(p.frequencia_hz, 0.002)
        fator = p.fator_potencia

    tensao = min(LIMITE_TENSAO_V, max(0.0, tensao))
    corrente = max(0.0, corrente)
    vibracao = max(0.0, vibracao)
    frequencia = min(LIMITE_FREQUENCIA_HZ, max(0.0, frequencia))

    return {
        "maquina_id": maquina_id,
        "status_atual": status,
        "tensao_volt": round(tensao, 1),
        "corrente_ampere": round(corrente, 2),
        "potencia_watt": round(calcular_potencia(tensao, corrente, fator), 1),
        "vibracao_rms": round(vibracao, 2),
        "frequencia_hz": round(frequencia, 2),
    }
