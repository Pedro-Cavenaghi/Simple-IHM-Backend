import asyncio

import numpy as np
import pandas as pd
import pytest

from ml import treinar
from ml.avaliacao import (
    avaliar_prognostico,
    normal_limpo,
    preparar_dados,
)
from ml.features import LEITURAS_POR_MINUTO
from ml.modelo import LimiaresEstatisticos, ModeloFalhas, confirmar
from ml.tendencia import minutos_ate_limite
from simulador import gerar_dataset


# ---------- confirmação por persistência ----------


def test_confirmar_exige_leituras_seguidas():
    sinais = np.array([1, 1, 0, 1, 1, 1, 1, 0], dtype=bool)

    alertas = confirmar(sinais, 3)

    assert alertas.tolist() == [0, 0, 0, 0, 0, 1, 1, 0]


def test_confirmar_com_uma_leitura_devolve_o_proprio_sinal():
    sinais = np.array([0, 1, 0], dtype=bool)

    assert confirmar(sinais, 1).tolist() == [0, 1, 0]


def test_limiares_estatisticos():
    normal = pd.DataFrame({"a": [0.0, 0.1, -0.1, 0.05], "b": [0.0, 0.0, 0.01, 0.0]})
    limiares = LimiaresEstatisticos(quantil=1.0).fit(normal)

    resultado = limiares.detectar(pd.DataFrame({"a": [0.05, 0.5], "b": [0.0, 0.0]}))

    assert resultado.tolist() == [False, True]


# ---------- regressão de tendência ----------


def serie_por_minuto(funcao, minutos=3):
    t = np.arange(minutos * LEITURAS_POR_MINUTO) / LEITURAS_POR_MINUTO
    return funcao(t), t[-1]


def test_reta_prevista_exatamente():
    # Vibração relativa sobe 0,2 por minuto; está em 0,6 → faltam 2 min para 1,0
    y, agora = serie_por_minuto(lambda t: 0.6 - 0.2 * (3 - 1 / 30) + 0.2 * t)

    assert minutos_ate_limite(y, limite=1.0, grau=1) == pytest.approx(2.0)


def test_curva_acelerada_prevista_pelo_termo_quadratico():
    y, agora = serie_por_minuto(lambda t: 0.05 * t**2)
    real = np.sqrt(1.0 / 0.05) - agora

    previsto_quadratico = minutos_ate_limite(y, limite=1.0, grau=2)
    previsto_reta = minutos_ate_limite(y, limite=1.0, grau=1)

    assert previsto_quadratico == pytest.approx(real, rel=1e-6)
    assert previsto_reta > real  # a reta prevê tarde demais


@pytest.mark.parametrize("grau", [1, 2])
def test_sem_tendencia_de_alta_nao_preve(grau):
    estavel, _ = serie_por_minuto(lambda t: 0.1 + 0 * t)
    caindo, _ = serie_por_minuto(lambda t: 0.5 - 0.1 * t)

    assert minutos_ate_limite(estavel, 1.0, grau) is None
    assert minutos_ate_limite(caindo, 1.0, grau) is None


def test_ja_acima_do_limite_retorna_zero():
    y, _ = serie_por_minuto(lambda t: 1.5 + 0 * t)

    assert minutos_ate_limite(y, 1.0) == 0.0


def test_serie_invalida_nao_preve():
    assert minutos_ate_limite(np.array([0.1, np.nan, 0.3]), 1.0) is None
    assert minutos_ate_limite(np.array([0.1]), 1.0) is None


def test_avaliar_prognostico_ignora_marcos_e_historico_insuficiente():
    dados = pd.DataFrame(
        {
            "evento": [0, 0, 0, 0, 0],
            "cenario": ["desgaste_rolamento"] * 5,
            "vibracao_relativa": [0.1, 0.2, 0.4, 0.8, 1.2],
            "vibracao_rms_desvio": [0.1, 0.2, 0.4, 1.0, 1.2],
            "posicao": [0, 1, 2, 3, 4],
        }
    )

    resumo, previsoes = avaliar_prognostico(
        dados, limite=1.0, marcos=(0.3, 1.5), janela=10
    )

    assert resumo["previsoes"] == 0
    assert previsoes.empty


# ---------- pipeline completo ----------


@pytest.fixture(scope="module")
def dados(tmp_path_factory):
    saida = tmp_path_factory.mktemp("ml") / "dataset.csv"
    asyncio.run(
        gerar_dataset.gerar(
            saida,
            sessoes=3,
            horas=1.5,
            intervalo_s=2,
            seed=7,
            pausa_min_s=180,
            pausa_max_s=360,
        )
    )
    return preparar_dados(pd.read_csv(saida))


def test_preparar_dados_marca_eventos_e_transicoes(dados):
    falhas = dados[dados["evento"] >= 0]

    assert len(falhas) > 0
    assert (falhas["cenario"] != "normal").all()
    assert (dados.loc[dados["evento"] < 0, "cenario"] == "normal").all()
    # Cada evento é de um único tipo, máquina e sessão
    assert (
        (falhas.groupby("evento")[["cenario", "maquina_id", "sessao"]].nunique() == 1)
        .all()
        .all()
    )
    assert dados["transicao"].any()
    assert not (dados["transicao"] & (dados["cenario"] != "normal")).any()
    assert normal_limpo(dados).sum() > 0


def test_divisao_por_sessao_nao_mistura(dados):
    treino, teste = treinar.dividir_por_sessao(dados, sessoes_teste=1)

    assert set(dados.loc[treino, "sessao"]).isdisjoint(dados.loc[teste, "sessao"])
    with pytest.raises(ValueError):
        treinar.dividir_por_sessao(dados, sessoes_teste=3)


def test_treino_completo_gera_modelo_util(dados, tmp_path, monkeypatch):
    monkeypatch.setattr(treinar, "SESSOES_TESTE", 1)
    modelo, metricas = treinar.treinar(dados)

    assert metricas["deteccao"]["falhas"] > 0
    assert metricas["deteccao"]["taxa_deteccao"] > 0.8
    assert metricas["diagnostico"]["acuracia"] > 0.7
    assert set(metricas["dados"]["sessoes_treino"]).isdisjoint(
        metricas["dados"]["sessoes_teste"]
    )

    caminho = tmp_path / "modelo.joblib"
    modelo.salvar(caminho)
    carregado = ModeloFalhas.carregar(caminho)
    amostra = dados[dados["valido"]].head(50)
    assert (carregado.detectar(amostra) == modelo.detectar(amostra)).all()
    classes, confianca = carregado.diagnosticar(amostra)
    assert len(classes) == 50
    assert ((0 <= confianca) & (confianca <= 1)).all()


def test_carregar_arquivo_que_nao_e_modelo(tmp_path):
    import joblib

    caminho = tmp_path / "outro.joblib"
    joblib.dump({"nao": "modelo"}, caminho)

    with pytest.raises(TypeError):
        ModeloFalhas.carregar(caminho)


def test_linha_de_comando(tmp_path, monkeypatch, capsys):
    saida = tmp_path / "dataset.csv"
    asyncio.run(
        gerar_dataset.gerar(
            saida,
            sessoes=3,
            horas=1,
            intervalo_s=2,
            seed=3,
            pausa_min_s=120,
            pausa_max_s=240,
        )
    )
    monkeypatch.setattr(treinar, "SESSOES_TESTE", 1)

    treinar.main(
        [
            "--dataset",
            str(saida),
            "--saida",
            str(tmp_path / "m.joblib"),
            "--metricas",
            str(tmp_path / "m.json"),
        ]
    )

    assert (tmp_path / "m.joblib").exists()
    assert "Detecção" in capsys.readouterr().out

