"""Garante que o modelo versionado funciona com as dependências instaladas.

Se uma atualização do scikit-learn chegar sem retreino, a CI falha aqui em vez
de o monitor de ML desligar em produção.
"""

import warnings

import numpy as np
import pandas as pd
import pytest
import sklearn

import app.monitor as monitor
from ml.features import COLUNAS_FEATURES
from ml.modelo import ModeloFalhas


@pytest.fixture(scope="module")
def modelo():
    with warnings.catch_warnings():
        warnings.simplefilter("error", sklearn.exceptions.InconsistentVersionWarning)
        return ModeloFalhas.carregar(monitor.CAMINHO_MODELO)


def test_modelo_foi_treinado_com_o_sklearn_instalado(modelo):
    assert modelo.versao_sklearn == sklearn.__version__


def test_modelo_versionado_faz_previsoes(modelo):
    linha = pd.DataFrame([np.zeros(len(COLUNAS_FEATURES))], columns=COLUNAS_FEATURES)

    pontuacao = modelo.pontuacao_anomalia(linha)
    classes, probabilidades = modelo.diagnosticar(linha)

    assert np.isfinite(pontuacao).all()
    assert classes[0] in modelo.diagnostico.classes_
    assert 0 <= probabilidades[0] <= 1


def test_carregar_sem_aviso_com_versao_correta():
    assert monitor.carregar_modelo() is not None
    assert monitor.aviso_modelo is None


def test_versao_diferente_gera_aviso(monkeypatch):
    monkeypatch.setattr(sklearn, "__version__", "0.0.0")

    assert monitor.carregar_modelo() is not None
    assert "scikit-learn" in monitor.aviso_modelo

    monkeypatch.undo()
    monitor.carregar_modelo()


def test_modelo_ausente_gera_aviso(tmp_path):
    assert monitor.carregar_modelo(tmp_path / "nao_existe.joblib") is None
    assert "desligado" in monitor.aviso_modelo

    monitor.carregar_modelo()
