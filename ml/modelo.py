"""Modelos de falha: detecção (está fora do padrão?) e diagnóstico (que falha é?).

O ModeloFalhas reúne tudo o que a API precisa e é salvo num único .joblib.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.tree import DecisionTreeClassifier

from ml.features import COLUNAS_DETECTOR, COLUNAS_DIAGNOSTICO


def confirmar(sinais: np.ndarray, leituras: int) -> np.ndarray:
    """Só confirma um alerta quando o sinal se repete em `leituras` seguidas.

    Evita alertas por uma leitura ruidosa isolada. alerta[i] é True se
    sinais[i - leituras + 1 .. i] forem todos True.
    """
    sinais = np.asarray(sinais, dtype=bool)
    if leituras <= 1:
        return sinais.copy()
    seguidas = np.convolve(sinais.astype(int), np.ones(leituras, dtype=int))
    seguidas = seguidas[: len(sinais)]
    return seguidas >= leituras


class LimiaresEstatisticos:
    """Linha de base para comparação: alerta se alguma feature passar do limite.

    O limite de cada feature é o quantil `quantil` do seu valor absoluto na
    operação normal. É o que um engenheiro faria "na mão", sem ML.
    """

    def __init__(self, quantil: float = 0.999):
        self.quantil = quantil
        self.limites: pd.Series | None = None

    def fit(self, X_normal: pd.DataFrame) -> "LimiaresEstatisticos":
        self.limites = X_normal.abs().quantile(self.quantil)
        return self

    def detectar(self, X: pd.DataFrame) -> np.ndarray:
        return (X.abs() > self.limites).any(axis=1).to_numpy()


@dataclass
class ModeloFalhas:
    detector: IsolationForest
    limiar_detector: float  # score_samples abaixo disto = anômalo
    diagnostico: DecisionTreeClassifier
    leituras_confirmacao: int
    limite_vibracao: float  # vibração relativa que define "passou do limite"
    colunas_detector: tuple[str, ...] = COLUNAS_DETECTOR
    colunas_diagnostico: tuple[str, ...] = COLUNAS_DIAGNOSTICO
    metricas: dict = field(default_factory=dict)
    versao_sklearn: str = sklearn.__version__
    treinado_em: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def pontuacao_anomalia(self, X: pd.DataFrame) -> np.ndarray:
        """Quanto maior, mais anômalo. Acima de 0 = além do limiar."""
        return self.limiar_detector - self.detector.score_samples(
            X[list(self.colunas_detector)]
        )

    def detectar(self, X: pd.DataFrame) -> np.ndarray:
        return self.pontuacao_anomalia(X) > 0

    def diagnosticar(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Classe mais provável e sua probabilidade, para cada linha."""
        probabilidades = self.diagnostico.predict_proba(
            X[list(self.colunas_diagnostico)]
        )
        melhor = probabilidades.argmax(axis=1)
        return self.diagnostico.classes_[melhor], probabilidades.max(axis=1)

    def salvar(self, caminho: Path) -> None:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, caminho, compress=3)

    @staticmethod
    def carregar(caminho: Path) -> "ModeloFalhas":
        modelo = joblib.load(caminho)
        if not isinstance(modelo, ModeloFalhas):
            raise TypeError(f"{caminho} não contém um ModeloFalhas")
        return modelo
