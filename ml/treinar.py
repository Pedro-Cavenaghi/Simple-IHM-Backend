"""Treina e avalia os modelos de falha a partir do dataset rotulado.

    python -m ml.treinar

Lê ml/dados/dataset.csv (gerado por `python -m simulador.gerar_dataset`),
separa treino e teste por sessão, treina o detector e o diagnóstico, avalia
nas sessões de teste e salva:
- ml/modelos/modelo_falhas.joblib: o modelo que a API vai carregar;
- ml/modelos/metricas.json: os resultados da avaliação.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.tree import DecisionTreeClassifier

from ml.avaliacao import (
    avaliar_deteccao,
    avaliar_diagnostico,
    avaliar_prognostico,
    normal_limpo,
    preparar_dados,
)
from ml.features import COLUNAS_DETECTOR, COLUNAS_DIAGNOSTICO, JANELA_CURTA
from ml.modelo import ModeloFalhas, confirmar

SEMENTE = 42
SESSOES_TESTE = 2
# Fração de leituras normais que o detector pode marcar como anômalas, antes da
# confirmação por persistência (que derruba ainda mais os alarmes falsos)
TAXA_FALSO_POSITIVO = 0.001
LEITURAS_CONFIRMACAO = 5  # 10 s seguidos de anomalia para confirmar um alerta
PROFUNDIDADE_ARVORE = 6
LIMITE_VIBRACAO = 1.0  # o dobro da vibração normal


def dividir_por_sessao(dados: pd.DataFrame, sessoes_teste: int = SESSOES_TESTE):
    """As últimas sessões viram teste. Nunca a mesma sessão dos dois lados."""
    sessoes = sorted(dados["sessao"].unique())
    if len(sessoes) <= sessoes_teste:
        raise ValueError(
            f"São necessárias mais de {sessoes_teste} sessões (há {len(sessoes)})"
        )
    teste = dados["sessao"].isin(sessoes[-sessoes_teste:])
    return ~teste, teste


def linhas_detector(dados: pd.DataFrame) -> pd.Series:
    """Operação normal limpa: o detector aprende só como é o 'normal'."""
    return dados["valido"] & normal_limpo(dados)


def linhas_diagnostico(dados: pd.DataFrame) -> pd.Series:
    """Leituras de falha depois que a janela curta já 'enxerga' a falha."""
    return (
        dados["valido"]
        & (dados["evento"] >= 0)
        & (dados["posicao_no_evento"] >= JANELA_CURTA)
    )


def treinar_detector(
    X_normal: pd.DataFrame, taxa_falso_positivo: float = TAXA_FALSO_POSITIVO
) -> tuple[IsolationForest, float]:
    """Isolation Forest treinado só com operação normal.

    Não precisa de exemplos de falha: aprende o que é normal e estranha o resto.
    Por isso também acusa falhas de tipos que nunca viu.
    """
    detector = IsolationForest(n_estimators=200, max_samples=512, random_state=SEMENTE)
    detector.fit(X_normal)
    limiar = float(np.quantile(detector.score_samples(X_normal), taxa_falso_positivo))
    return detector, limiar


def treinar_diagnostico(
    X_falhas: pd.DataFrame, y: pd.Series, profundidade: int = PROFUNDIDADE_ARVORE
) -> DecisionTreeClassifier:
    """Árvore de decisão que diz qual falha é. Rasa o bastante para ser lida."""
    arvore = DecisionTreeClassifier(
        max_depth=profundidade,
        min_samples_leaf=20,
        class_weight="balanced",  # sobrecarga tem bem menos linhas que desgaste
        random_state=SEMENTE,
    )
    return arvore.fit(X_falhas, y)


def treinar(dados: pd.DataFrame) -> tuple[ModeloFalhas, dict]:
    treino, teste = dividir_por_sessao(dados)

    detector, limiar = treinar_detector(
        dados.loc[treino & linhas_detector(dados), list(COLUNAS_DETECTOR)]
    )
    filtro = treino & linhas_diagnostico(dados)
    arvore = treinar_diagnostico(
        dados.loc[filtro, list(COLUNAS_DIAGNOSTICO)], dados.loc[filtro, "cenario"]
    )

    modelo = ModeloFalhas(
        detector=detector,
        limiar_detector=limiar,
        diagnostico=arvore,
        leituras_confirmacao=LEITURAS_CONFIRMACAO,
        limite_vibracao=LIMITE_VIBRACAO,
    )
    metricas = avaliar(modelo, dados[teste & dados["valido"]].reset_index(drop=True))
    metricas["dados"] = {
        "sessoes_treino": sorted(dados.loc[treino, "sessao"].unique()),
        "sessoes_teste": sorted(dados.loc[teste, "sessao"].unique()),
        "linhas_treino_detector": int((treino & linhas_detector(dados)).sum()),
        "linhas_treino_diagnostico": int(filtro.sum()),
    }
    modelo.metricas = metricas
    return modelo, metricas


def alertas_confirmados(modelo: ModeloFalhas, dados: pd.DataFrame) -> np.ndarray:
    """Anomalias do detector, confirmadas por persistência em cada máquina."""
    brutos = modelo.detectar(dados)
    alertas = np.zeros(len(dados), dtype=bool)
    for indices in dados.groupby(["sessao", "maquina_id"], sort=False).indices.values():
        alertas[indices] = confirmar(brutos[indices], modelo.leituras_confirmacao)
    return alertas


def avaliar(modelo: ModeloFalhas, teste: pd.DataFrame) -> dict:
    alertas = alertas_confirmados(modelo, teste)
    deteccao, _ = avaliar_deteccao(teste, alertas)
    classes, _ = modelo.diagnosticar(teste)
    diagnostico, _ = avaliar_diagnostico(
        teste,
        modelo.pontuacao_anomalia(teste),
        classes,
        modelo.leituras_confirmacao,
    )
    prognostico, _ = avaliar_prognostico(teste, modelo.limite_vibracao)
    return {
        "deteccao": deteccao,
        "diagnostico": diagnostico,
        "prognostico": prognostico,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Treina os modelos de falha")
    parser.add_argument("--dataset", type=Path, default=Path("ml/dados/dataset.csv"))
    parser.add_argument(
        "--saida", type=Path, default=Path("ml/modelos/modelo_falhas.joblib")
    )
    parser.add_argument(
        "--metricas", type=Path, default=Path("ml/modelos/metricas.json")
    )
    args = parser.parse_args(argv)

    inicio = time.perf_counter()
    dados = preparar_dados(pd.read_csv(args.dataset))
    modelo, metricas = treinar(dados)
    modelo.salvar(args.saida)
    args.metricas.parent.mkdir(parents=True, exist_ok=True)
    args.metricas.write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    d, g, p = metricas["deteccao"], metricas["diagnostico"], metricas["prognostico"]
    print(f"Treinado em {time.perf_counter() - inicio:.0f}s → {args.saida}")
    print(
        f"Detecção:    {d['taxa_deteccao']:.1%} das {d['falhas']} falhas de teste, "
        f"atraso mediano {d['atraso_mediano_s']:.0f}s, "
        f"{d['alarmes_falsos_por_maquina_dia']:.2f} alarmes falsos por máquina-dia"
    )
    print(
        f"Diagnóstico: {g['acuracia']:.1%} de acerto em "
        f"{g['falhas_diagnosticadas']} falhas detectadas"
    )
    print(
        f"Prognóstico: erro médio de {p['erro_absoluto_medio_min']:.1f} min "
        f"em {p['previsoes']} previsões de desgaste"
    )


if __name__ == "__main__":
    main()
