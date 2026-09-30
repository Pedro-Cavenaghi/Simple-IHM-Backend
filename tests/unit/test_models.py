import pytest
from pydantic import ValidationError

from app.models import LeituraSensor


def test_leitura_sensor_valida():
    leitura = LeituraSensor(
        maquina_id=1,
        vibracao_rms=1.5,
        corrente_ampere=10.0,
        tensao_volt=220.0,
        potencia_watt=2000.0,
        frequencia_hz=60.0,
        status_atual="Ativa",
    )

    assert leitura.maquina_id == 1
    assert leitura.tensao_volt == 220.0


def test_leitura_sensor_rejeita_tensao_invalida():
    with pytest.raises(ValidationError):
        LeituraSensor(
            maquina_id=1,
            vibracao_rms=1.5,
            corrente_ampere=10.0,
            tensao_volt=500.0,
            potencia_watt=2000.0,
            frequencia_hz=60.0,
            status_atual="Ligada",
        )