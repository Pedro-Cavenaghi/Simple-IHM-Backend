import numpy as np
import pandas as pd
import pytest

from ml.features import (
    COLUNAS_DETECTOR,
    COLUNAS_DIAGNOSTICO,
    COLUNAS_FEATURES,
    LEITURAS_AQUECIMENTO,
    SINAIS,
    TAMANHO_HISTORICO,
    calcular_features,
    calcular_features_por_grupo,
    inclinacao_movel,
    vibracao_relativa,
)


def leituras_constantes(n=1200, **valores):
    base = {
        "tensao_volt": 220.0,
        "corrente_ampere": 15.0,
        "potencia_watt": 2805.0,
        "vibracao_rms": 2.0,
        "frequencia_hz": 60.0,
    }
    base.update(valores)
    return pd.DataFrame({sinal: np.full(n, base[sinal]) for sinal in SINAIS})


def leituras_ruidosas(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    df = leituras_constantes(n)
    for sinal in SINAIS:
        df[sinal] = df[sinal] * (1 + rng.normal(0, 0.03, n))
    return df


def test_inclinacao_movel_recupera_reta_exata():
    serie = pd.Series(3.0 + 0.5 * np.arange(100))

    inclinacao = inclinacao_movel(serie, janela=10)

    assert inclinacao.iloc[:9].isna().all()
    assert np.allclose(inclinacao.iloc[9:], 0.5)


def test_inclinacao_movel_igual_a_regressao_linear():
    rng = np.random.default_rng(1)
    serie = pd.Series(rng.normal(size=200).cumsum())

    inclinacao = inclinacao_movel(serie, janela=30)

    for fim in (29, 100, 199):
        janela = serie.iloc[fim - 29 : fim + 1].to_numpy()
        esperado = np.polyfit(np.arange(30), janela, 1)[0]
        assert inclinacao.iloc[fim] == pytest.approx(esperado)


def test_operacao_constante_tem_features_zeradas():
    features = calcular_features(leituras_constantes())

    validas = features.dropna()
    assert len(validas) > 0
    assert np.allclose(validas.to_numpy(), 0.0)


def test_aquecimento_gera_nan_e_depois_features_completas():
    features = calcular_features(leituras_ruidosas())

    assert features.iloc[: LEITURAS_AQUECIMENTO - 1].isna().any(axis=1).all()
    assert features.iloc[LEITURAS_AQUECIMENTO:].notna().all(axis=1).all()
    assert tuple(features.columns) == COLUNAS_FEATURES


def test_aumento_de_vibracao_aparece_como_desvio_positivo():
    df = leituras_constantes()
    df.loc[1100:, "vibracao_rms"] = 4.0  # o dobro do normal

    features = calcular_features(df)

    assert features["vibracao_rms_desvio"].iloc[-1] == pytest.approx(1.0)
    assert features["corrente_ampere_desvio"].iloc[-1] == pytest.approx(0.0)


def test_features_nao_usam_leituras_futuras():
    """Mudar o futuro não pode mudar as features do passado (sem vazamento)."""
    df = leituras_ruidosas()
    original = calcular_features(df)

    alterado = df.copy()
    alterado.loc[800:, "vibracao_rms"] *= 5
    alterado.loc[800:, "corrente_ampere"] *= 3
    recalculado = calcular_features(alterado)

    pd.testing.assert_frame_equal(original.iloc[:800], recalculado.iloc[:800])


def test_historico_da_api_reproduz_a_feature_do_treino():
    """Com TAMANHO_HISTORICO leituras, a API calcula a mesma última feature do treino."""
    df = leituras_ruidosas(n=3000)
    treino = calcular_features(df).iloc[-1]

    historico = df.iloc[-TAMANHO_HISTORICO:].reset_index(drop=True)
    api = calcular_features(historico).iloc[-1]

    pd.testing.assert_series_equal(treino, api, check_names=False, rtol=1e-9)


def test_features_por_grupo_nao_misturam_maquinas():
    a = leituras_ruidosas(seed=1).assign(sessao="s1", maquina_id=1)
    b = leituras_constantes(vibracao_rms=50.0).assign(sessao="s1", maquina_id=2)
    for df in (a, b):
        df["registrado_em_utc"] = pd.RangeIndex(len(df)).astype(str).str.zfill(6)
    juntas = pd.concat([a, b], ignore_index=True)

    features = calcular_features_por_grupo(juntas)

    pd.testing.assert_frame_equal(
        features.iloc[: len(a)].reset_index(drop=True),
        calcular_features(a).reset_index(drop=True),
    )
    assert np.allclose(features.iloc[len(a) :].dropna().to_numpy(), 0.0)


def test_vibracao_relativa():
    df = leituras_constantes()
    df.loc[1100:, "vibracao_rms"] = 3.0

    relativa = vibracao_relativa(df)

    assert relativa.iloc[-1] == pytest.approx(0.5)


def test_detector_nao_usa_potencia_e_diagnostico_usa():
    assert not any(c.startswith("potencia") for c in COLUNAS_DETECTOR)
    assert "potencia_watt_desvio" in COLUNAS_DIAGNOSTICO
