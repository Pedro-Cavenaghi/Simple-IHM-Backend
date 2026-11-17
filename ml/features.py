"""Features de janela calculadas a partir das leituras de uma máquina.

Este é o único lugar onde as features são definidas. O treino (treinar.py) e a
API (fase 3) chamam a mesma função, para que o modelo veja em produção
exatamente o que viu no treino.

Cada leitura é descrita em relação à **linha de base da própria máquina**: a
vibração de 5,8 g é normal numa injetora e alarmante numa prensa. A linha de base
é a mediana dos últimos 30 minutos, sem os 3 minutos mais recentes (para que uma
falha em andamento não "puxe" a referência para cima).
"""

import numpy as np
import pandas as pd

SINAIS = (
    "tensao_volt",
    "corrente_ampere",
    "potencia_watt",
    "vibracao_rms",
    "frequencia_hz",
)

# Tamanhos em número de leituras (a ESP32 envia uma a cada 2 s)
LEITURAS_POR_MINUTO = 30
JANELA_CURTA = 15  # 30 s: média e ruído recentes
JANELA_TENDENCIA = 90  # 3 min: inclinação (tendência)
JANELA_BASE = 900  # 30 min: linha de base adaptativa
MIN_LEITURAS_BASE = 150  # 5 min de histórico mínimo para a linha de base

# Leituras necessárias para a primeira feature completa (aquecimento)
LEITURAS_AQUECIMENTO = MIN_LEITURAS_BASE + JANELA_TENDENCIA
# Leituras que a API precisa guardar por máquina para calcular a última feature
TAMANHO_HISTORICO = JANELA_BASE + JANELA_TENDENCIA

COLUNAS_FEATURES = tuple(
    f"{sinal}_{tipo}" for sinal in SINAIS for tipo in ("desvio", "ruido", "tendencia")
)

# A potência é redundante para *detectar* (é V × I × FP, e só dilui o detector),
# mas decisiva para *diagnosticar*: na sobrecarga ela sobe, na queda de tensão
# o motor compensa com mais corrente e ela quase não muda.
COLUNAS_DETECTOR = tuple(c for c in COLUNAS_FEATURES if not c.startswith("potencia"))
COLUNAS_DIAGNOSTICO = COLUNAS_FEATURES


def inclinacao_movel(serie: pd.Series, janela: int) -> pd.Series:
    """Inclinação da reta de mínimos quadrados em cada janela, por leitura.

    Forma fechada e vetorizada: b = (média(i·y) − média(i)·média(y)) / var(i),
    em que i é a posição da leitura. Equivale a ajustar uma regressão linear
    em cada janela, só que muito mais rápido.
    """
    posicao = pd.Series(np.arange(len(serie), dtype=float), index=serie.index)
    media_y = serie.rolling(janela).mean()
    media_i = posicao.rolling(janela).mean()
    media_iy = (posicao * serie).rolling(janela).mean()
    variancia_i = (janela**2 - 1) / 12
    return (media_iy - media_i * media_y) / variancia_i


def linha_de_base(serie: pd.Series) -> pd.Series:
    base = (
        serie.rolling(JANELA_BASE, min_periods=MIN_LEITURAS_BASE)
        .median()
        .shift(JANELA_TENDENCIA)
    )
    return base.where(base > 0)


def calcular_features(leituras: pd.DataFrame) -> pd.DataFrame:
    """Features de uma única máquina, com as leituras em ordem cronológica.

    Use apenas leituras com a máquina em operação (status 'Ativa'): parada,
    a máquina não tem comportamento a comparar. As primeiras
    LEITURAS_AQUECIMENTO linhas saem com NaN (histórico insuficiente).

    Cada feature usa só leituras passadas e a atual, nunca futuras.
    """
    features = {}
    for sinal in SINAIS:
        serie = leituras[sinal].astype(float)
        base = linha_de_base(serie)
        recente = serie.rolling(JANELA_CURTA)

        # Quanto a média recente está acima (+) ou abaixo (−) do normal: 0,5 = +50%
        features[f"{sinal}_desvio"] = recente.mean() / base - 1
        # Oscilação recente em relação ao normal (pega o desbalanceamento)
        features[f"{sinal}_ruido"] = recente.std() / base
        # Variação relativa por minuto nos últimos 3 min (pega o desgaste)
        features[f"{sinal}_tendencia"] = (
            inclinacao_movel(serie, JANELA_TENDENCIA) * LEITURAS_POR_MINUTO / base
        )
    return pd.DataFrame(features, index=leituras.index)[list(COLUNAS_FEATURES)]


def vibracao_relativa(leituras: pd.DataFrame) -> pd.Series:
    """Vibração em relação à linha de base: 0 = normal, 1,0 = o dobro do normal.

    Não é uma feature do modelo: é a série usada pela regressão de tendência
    (tendencia.py) para estimar quando a vibração vai cruzar o limite.
    """
    serie = leituras["vibracao_rms"].astype(float)
    return serie / linha_de_base(serie) - 1


def calcular_features_por_grupo(
    leituras: pd.DataFrame,
    grupo: tuple[str, ...] = ("sessao", "maquina_id"),
    ordem: str = "registrado_em_utc",
) -> pd.DataFrame:
    """Aplica calcular_features a cada máquina de cada sessão, sem misturá-las."""
    partes = [
        calcular_features(parte.sort_values(ordem))
        for _, parte in leituras.groupby(list(grupo), sort=False)
    ]
    return pd.concat(partes).reindex(leituras.index)
