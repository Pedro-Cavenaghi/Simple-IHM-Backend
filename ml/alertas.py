"""Regras do ciclo de vida de um alerta: quando abre, qual o diagnóstico, quando encerra.

São as MESMAS regras no monitor da API (app/monitor.py) e na avaliação offline
(avaliacao.py), para que as métricas reportadas meçam o que roda em produção.

- Abre: após `leituras_confirmacao` leituras anômalas seguidas.
- Diagnóstico: voto ponderado pela pontuação de anomalia. As leituras mais
  anômalas (o meio da falha) pesam mais que as da transição logo depois dela,
  quando as janelas ainda "lembram" a falha mas a árvore nunca foi treinada.
- Encerra: após LEITURAS_ENCERRAMENTO leituras normais seguidas (3 min, o tempo
  que as janelas levam para esquecer a falha). Com 1 min, o alerta fechava e
  reabria durante a transição, gerando alertas duplicados.
"""

from collections import defaultdict

import numpy as np

from ml.features import JANELA_TENDENCIA

LEITURAS_ENCERRAMENTO = JANELA_TENDENCIA


class VotacaoDiagnostico:
    def __init__(self):
        self.pesos: dict[str, float] = defaultdict(float)

    def votar(self, classe: str, pontuacao: float) -> None:
        if pontuacao > 0:
            self.pesos[classe] += pontuacao

    def resultado(self) -> tuple[str | None, float | None]:
        """Classe vencedora e sua fatia do peso total (a confiança, de 0 a 1)."""
        total = sum(self.pesos.values())
        if total <= 0:
            return None, None
        classe = max(self.pesos, key=self.pesos.get)
        return classe, self.pesos[classe] / total


def simular_alertas(
    pontuacoes: np.ndarray,
    leituras_confirmacao: int,
    leituras_encerramento: int = LEITURAS_ENCERRAMENTO,
) -> list[tuple[int, int]]:
    """Intervalos (início, fim) dos alertas numa sequência de leituras de uma máquina.

    `início` é a leitura que confirmou o alerta e `fim` a que o encerrou (ou a
    última leitura, se ele ainda estiver aberto).
    """
    alertas = []
    anomalias = normais = 0
    inicio = None
    for i, pontuacao in enumerate(np.asarray(pontuacoes, dtype=float)):
        if pontuacao > 0:
            anomalias, normais = anomalias + 1, 0
        else:
            anomalias, normais = 0, normais + 1

        if inicio is None:
            if anomalias >= leituras_confirmacao:
                inicio = i
        elif normais >= leituras_encerramento:
            alertas.append((inicio, i))
            inicio = None
    if inicio is not None:
        alertas.append((inicio, len(pontuacoes) - 1))
    return alertas
