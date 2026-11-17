import numpy as np
import pandas as pd
import pytest

from ml.alertas import VotacaoDiagnostico, simular_alertas
from ml.avaliacao import avaliar_diagnostico


def test_voto_ponderado_pela_pontuacao():
    votacao = VotacaoDiagnostico()
    # Poucas leituras muito anômalas (a falha) contra muitas pouco anômalas (transição)
    for _ in range(5):
        votacao.votar("sobrecarga", 1.0)
    for _ in range(20):
        votacao.votar("desgaste_rolamento", 0.1)

    classe, confianca = votacao.resultado()

    assert classe == "sobrecarga"
    assert confianca == pytest.approx(5 / 7)


def test_leituras_normais_nao_votam():
    votacao = VotacaoDiagnostico()
    votacao.votar("sobrecarga", -0.5)

    assert votacao.resultado() == (None, None)


def test_simular_alertas_abre_e_encerra():
    pontuacoes = [-1] * 5 + [1] * 4 + [-1] * 3 + [1] + [-1] * 6

    alertas = simular_alertas(
        np.array(pontuacoes), leituras_confirmacao=3, leituras_encerramento=4
    )

    # Abre na 3ª anômala (índice 7); a anomalia isolada no índice 12 mantém o alerta
    assert alertas == [(7, 16)]


def test_alerta_aberto_ate_o_fim_da_serie():
    alertas = simular_alertas(np.array([1, 1, 1, 1]), 2, 10)

    assert alertas == [(1, 3)]


def test_anomalia_curta_demais_nao_abre():
    assert simular_alertas(np.array([1, 1, -1, 1, 1, -1]), 3, 5) == []


def test_avaliar_diagnostico_por_alerta():
    cenario = ["normal"] * 4 + ["sobrecarga"] * 4 + ["normal"] * 8
    dados = pd.DataFrame(
        {
            "sessao": "s",
            "maquina_id": 1,
            "cenario": cenario,
            "evento": [-1] * 4 + [0] * 4 + [-1] * 8,
        }
    )
    pontuacoes = np.array([-1] * 4 + [2, 2, 2, 2] + [0.1, 0.1, 0.1] + [-1] * 5)
    classes = np.array(
        ["normal"] * 4 + ["sobrecarga"] * 4 + ["desgaste_rolamento"] * 3 + ["x"] * 5
    )

    resumo, resultado = avaliar_diagnostico(dados, pontuacoes, classes, 2, 4)

    assert resumo["alertas"] == 1
    assert resumo["alertas_sem_falha"] == 0
    assert resumo["acuracia"] == 1.0
    assert resultado.iloc[0]["previsto"] == "sobrecarga"
