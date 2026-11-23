import numpy as np
import pandas as pd
import pytest

from ml.features import (
    COLUNAS_FEATURES,
    LEITURAS_AQUECIMENTO,
    SINAIS,
    calcular_features,
    linhas_de_base_atuais,
    vibracao_relativa,
)
from ml.robustez import AQUECIMENTO, avaliar_cenario, degrau, rampa, simular_monitor


class ModeloPorDesvio:
    """Anômalo quando a vibração recente foge 30% da linha de base."""

    leituras_confirmacao = 3

    def pontuacao_anomalia(self, features):
        return features["vibracao_rms_desvio"].abs().to_numpy() - 0.3


def leituras(total, semente=1):
    rng = np.random.default_rng(semente)
    return pd.DataFrame(
        {sinal: 100 * (1 + rng.normal(0, 0.005, total)) for sinal in SINAIS}
    )


def test_base_fixa_mede_contra_a_referencia_congelada():
    dados = leituras(LEITURAS_AQUECIMENTO + 30)
    dados["vibracao_rms"] = 200.0
    base = {sinal: 100.0 for sinal in SINAIS}

    features = calcular_features(dados, base).iloc[-1]

    assert features["vibracao_rms_desvio"] == pytest.approx(1.0)
    assert vibracao_relativa(dados, base).iloc[-1] == pytest.approx(1.0)
    assert list(features.index) == list(COLUNAS_FEATURES)


def test_linhas_de_base_atuais():
    assert linhas_de_base_atuais(leituras(50)) is None

    base = linhas_de_base_atuais(leituras(LEITURAS_AQUECIMENTO + 10))

    assert set(base) == set(SINAIS)
    assert base["tensao_volt"] == pytest.approx(100, abs=1)


def test_falha_longa_mantem_um_unico_alerta_aberto():
    total = AQUECIMENTO + 1500
    dados = leituras(total)
    dados["vibracao_rms"] *= degrau(("vibracao_rms",), 1.6, 1500)(total)["vibracao_rms"]

    alertas = simular_monitor(ModeloPorDesvio(), dados)

    assert len(alertas) == 1
    assert alertas[0][1] == total - 1


def test_volta_ao_normal_encerra_sem_novo_alerta():
    total = AQUECIMENTO + 1200 + 900
    dados = leituras(total)
    dados["vibracao_rms"] *= degrau(("vibracao_rms",), 1.6, 1200)(total)["vibracao_rms"]

    alertas = simular_monitor(ModeloPorDesvio(), dados, leituras_encerramento=90)

    assert len(alertas) == 1
    assert AQUECIMENTO + 1200 < alertas[0][1] < total - 1


def test_avaliar_cenario_resume_a_falha():
    resultado = avaliar_cenario(
        ModeloPorDesvio(),
        [leituras(AQUECIMENTO + 1200, semente=s) for s in (1, 2)],
        rampa(900),
        900,
        apos=300,
    )

    assert resultado["maquinas"] == 2
    assert resultado["taxa_deteccao"] == 1.0
    assert resultado["cobertura_da_falha"] > 0
    assert resultado["maquinas_com_alerta_apos_o_fim"] == 0


def test_avaliar_cenario_sem_dados_suficientes():
    assert (
        avaliar_cenario(
            ModeloPorDesvio(), [leituras(100)], degrau(("vibracao_rms",), 1.6, 50), 50
        )
        is None
    )
