"""Mede o monitor em falhas longas, que as sessões de coleta não contêm.

    python -m ml.robustez

Injeta falhas nas leituras normais das sessões de teste e aplica as regras do
monitor da API, com a linha de base congelada durante o alerta. O resultado vai
para a chave "robustez" de ml/modelos/metricas.json, sem alterar o modelo.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from ml.alertas import LEITURAS_ENCERRAMENTO, fora_da_faixa
from ml.avaliacao import normal_limpo, preparar_dados
from ml.features import (
    JANELA_TENDENCIA,
    LEITURAS_POR_MINUTO,
    SINAIS,
    TAMANHO_HISTORICO,
    calcular_features,
    linhas_de_base_atuais,
)

AQUECIMENTO = 40 * LEITURAS_POR_MINUTO  # operação normal antes da falha
Fatores = Callable[[int], dict[str, float | np.ndarray]]


def _pontuar(
    modelo, leituras: pd.DataFrame, base=None
) -> tuple[np.ndarray, np.ndarray]:
    """Pontuação de anomalia e, com base congelada, sinais fora da faixa."""
    features = calcular_features(leituras, base)
    validas = features.notna().all(axis=1).to_numpy()
    pontuacoes = np.full(len(features), -1.0)
    if validas.any():
        pontuacoes[validas] = modelo.pontuacao_anomalia(features[validas])
    fora = fora_da_faixa(features) if base else np.zeros(len(features), dtype=bool)
    return pontuacoes, fora


def _primeira_sequencia(mascara: np.ndarray, tamanho: int) -> int | None:
    """Posição em que `tamanho` valores True seguidos se completam."""
    seguidas = 0
    for i, valor in enumerate(mascara):
        seguidas = seguidas + 1 if valor else 0
        if seguidas >= tamanho:
            return i
    return None


def simular_monitor(
    modelo,
    leituras: pd.DataFrame,
    leituras_encerramento: int = LEITURAS_ENCERRAMENTO,
) -> list[tuple[int, int]]:
    """Intervalos (início, fim) dos alertas, com as regras de app/monitor.py."""
    leituras = leituras.reset_index(drop=True)
    total = len(leituras)
    alertas = []
    historico = np.array([], dtype=int)
    proxima = 0

    while proxima < total:
        indices = np.concatenate([historico, np.arange(proxima, total)])
        pontuacoes, _ = _pontuar(modelo, leituras.iloc[indices])
        achou = _primeira_sequencia(
            pontuacoes[len(historico) :] > 0, modelo.leituras_confirmacao
        )
        if achou is None:
            break

        posicao = len(historico) + achou
        inicio = int(indices[posicao])
        janela = indices[: posicao + 1][-TAMANHO_HISTORICO:]
        base = linhas_de_base_atuais(leituras.iloc[janela])
        depois = np.arange(inicio + 1, total)
        pontos, fora = _pontuar(
            modelo, leituras.iloc[np.concatenate([janela, depois])], base
        )
        normais = (pontos <= 0) & ~fora
        fecha = _primeira_sequencia(normais[len(janela) :], leituras_encerramento)
        if fecha is None:
            alertas.append((inicio, total - 1))
            break

        fim = int(depois[fecha])
        alertas.append((inicio, fim))
        limpo = janela[:-JANELA_TENDENCIA] if base else janela
        recentes = np.arange(fim - leituras_encerramento + 1, fim + 1)
        historico = np.concatenate([limpo, recentes])[-TAMANHO_HISTORICO:]
        proxima = fim + 1
    return alertas


def degrau(sinais: tuple[str, ...], fator: float, duracao: int) -> Fatores:
    def aplicar(total: int) -> dict[str, np.ndarray]:
        valores = np.ones(total)
        valores[AQUECIMENTO : AQUECIMENTO + duracao] = fator
        return {sinal: valores for sinal in sinais}

    return aplicar


def rampa(duracao: int) -> Fatores:
    """Vibração acelerando até o dobro, como no desgaste de rolamento."""

    def aplicar(total: int) -> dict[str, np.ndarray]:
        valores = np.ones(total)
        valores[AQUECIMENTO : AQUECIMENTO + duracao] = (
            1 + (np.arange(duracao) / duracao) ** 2
        )
        return {"vibracao_rms": valores}

    return aplicar


def avaliar_cenario(
    modelo,
    bases: list[pd.DataFrame],
    fatores: Fatores,
    duracao: int,
    apos: int = 0,
) -> dict | None:
    """Detecção e cobertura da falha. `apos` observa a volta ao normal."""
    total = AQUECIMENTO + duracao + apos
    usadas = [base.iloc[:total].copy() for base in bases if len(base) >= total]
    if not usadas:
        return None

    atrasos, coberturas, por_falha, falsos = [], [], [], []
    fim_falha = AQUECIMENTO + duracao
    for leituras in usadas:
        for sinal, fator in fatores(total).items():
            leituras[sinal] = leituras[sinal] * fator
        alertas = simular_monitor(modelo, leituras)
        na_falha = [(a, b) for a, b in alertas if a >= AQUECIMENTO and a < fim_falha]
        coberto = np.zeros(total, dtype=bool)
        for a, b in na_falha:
            coberto[a : b + 1] = True
        coberturas.append(float(coberto[AQUECIMENTO:fim_falha].mean()))
        por_falha.append(len(na_falha))
        atrasos.append(
            (na_falha[0][0] - AQUECIMENTO) / LEITURAS_POR_MINUTO if na_falha else np.nan
        )
        falsos.append(any(a >= fim_falha for a, _ in alertas))

    detectadas = ~np.isnan(atrasos)
    resultado = {
        "maquinas": len(usadas),
        "taxa_deteccao": float(detectadas.mean()),
        "atraso_mediano_min": (
            float(np.nanmedian(atrasos)) if detectadas.any() else None
        ),
        "cobertura_da_falha": float(np.mean(coberturas)),
        "alertas_por_falha": float(np.mean(por_falha)),
    }
    if apos:
        resultado["maquinas_com_alerta_apos_o_fim"] = float(np.mean(falsos))
    return resultado


def avaliar_robustez(modelo, teste: pd.DataFrame) -> dict:
    """Cenários de falha longa sobre as leituras normais de teste."""
    limpo = teste[normal_limpo(teste)]
    bases = [
        grupo[list(SINAIS)].reset_index(drop=True)
        for _, grupo in limpo.groupby(["sessao", "maquina_id"], sort=True)
    ]
    minuto = LEITURAS_POR_MINUTO
    vibracao = ("vibracao_rms",)
    carga = ("corrente_ampere", "potencia_watt")
    cenarios = {
        "vibracao_x1_6_por_2h": (degrau(vibracao, 1.6, 120 * minuto), 120 * minuto, 0),
        "sobrecarga_x1_4_por_2h": (degrau(carga, 1.4, 120 * minuto), 120 * minuto, 0),
        "volta_ao_normal_apos_40min": (
            degrau(vibracao, 1.6, 40 * minuto),
            40 * minuto,
            40 * minuto,
        ),
        "desgaste_ate_2x_em_1h": (rampa(60 * minuto), 60 * minuto, 0),
        "desgaste_ate_2x_em_4h": (rampa(240 * minuto), 240 * minuto, 0),
    }
    resultado = {}
    for nome, (fatores, duracao, apos) in cenarios.items():
        medido = avaliar_cenario(modelo, bases, fatores, duracao, apos)
        if medido is not None:
            resultado[nome] = medido
    return resultado


def main(argv: list[str] | None = None) -> None:
    from ml.modelo import ModeloFalhas
    from ml.treinar import dividir_por_sessao

    parser = argparse.ArgumentParser(description="Mede o monitor em falhas longas")
    parser.add_argument("--dataset", type=Path, default=Path("ml/dados/dataset.csv"))
    parser.add_argument(
        "--modelo", type=Path, default=Path("ml/modelos/modelo_falhas.joblib")
    )
    parser.add_argument(
        "--metricas", type=Path, default=Path("ml/modelos/metricas.json")
    )
    args = parser.parse_args(argv)

    dados = preparar_dados(pd.read_csv(args.dataset))
    _, teste = dividir_por_sessao(dados)
    robustez = avaliar_robustez(
        ModeloFalhas.carregar(args.modelo),
        dados[teste & dados["valido"]].reset_index(drop=True),
    )
    metricas = json.loads(args.metricas.read_text(encoding="utf-8"))
    metricas["robustez"] = robustez
    args.metricas.write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(robustez, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
