import importlib

import pytest

import simulador.config as config


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, False),
        ("false", False),
        ("0", False),
        ("true", True),
        ("TRUE", True),
        (" 1 ", True),
        ("sim", True),
    ],
)
def test_iniciar_pausado(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("INICIAR_PAUSADO", raising=False)
    else:
        monkeypatch.setenv("INICIAR_PAUSADO", valor)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)

    assert importlib.reload(config).INICIAR_PAUSADO is esperado
