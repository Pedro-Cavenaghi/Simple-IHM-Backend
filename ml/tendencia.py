"""Prognóstico por regressão: quando a vibração vai passar do limite?

Ajusta uma curva à vibração relativa dos últimos minutos e projeta quando ela
cruza o limite. É a estimativa que vira a data da manutenção preditiva.

Por padrão a regressão tem um termo quadrático (y = a + b·t + c·t²). Continua
sendo regressão *linear* (linear nos coeficientes), mas acompanha o desgaste,
que acelera com o tempo. Uma reta simples prevê o cruzamento tarde demais:
veja a comparação em ml/analise.ipynb.
"""

import numpy as np
from sklearn.linear_model import LinearRegression

from ml.features import JANELA_TENDENCIA, LEITURAS_POR_MINUTO

GRAU_PADRAO = 2
JANELA_PADRAO = JANELA_TENDENCIA  # 3 min de leituras
HORIZONTE_MAXIMO_MIN = 7 * 24 * 60  # além disso, "sem previsão"


def _termos(minutos: np.ndarray, grau: int) -> np.ndarray:
    return np.column_stack([minutos**k for k in range(1, grau + 1)])


def ajustar_tendencia(vibracao_relativa: np.ndarray, grau: int = GRAU_PADRAO):
    """Regressão da vibração relativa contra o tempo em minutos."""
    y = np.asarray(vibracao_relativa, dtype=float)
    minutos = np.arange(len(y)) / LEITURAS_POR_MINUTO
    return LinearRegression().fit(_termos(minutos, grau), y)


def minutos_ate_limite(
    vibracao_relativa: np.ndarray, limite: float, grau: int = GRAU_PADRAO
) -> float | None:
    """Minutos até a vibração relativa atingir `limite`, a partir da última leitura.

    Retorna 0 se a curva ajustada já passou do limite, e None se ela não
    cruza o limite no horizonte (vibração estável ou caindo) ou se a série
    tem valores inválidos.
    """
    y = np.asarray(vibracao_relativa, dtype=float)
    if len(y) <= grau or not np.isfinite(y).all():
        return None

    reta = ajustar_tendencia(y, grau)
    agora = (len(y) - 1) / LEITURAS_POR_MINUTO
    if float(reta.predict(_termos(np.array([agora]), grau))[0]) >= limite:
        return 0.0

    # Raízes de  a + b·t + c·t² + ... − limite = 0, depois de "agora"
    coeficientes = [reta.intercept_ - limite, *reta.coef_]
    raizes = np.roots(coeficientes[::-1])
    futuras = [
        r.real
        for r in raizes
        if abs(r.imag) < 1e-9 and agora < r.real <= agora + HORIZONTE_MAXIMO_MIN
    ]
    if not futuras:
        return None
    return min(futuras) - agora
