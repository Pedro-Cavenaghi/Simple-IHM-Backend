import random

import pytest

from app.models import LeituraSensor
from simulador.fisica import (
    CENARIOS,
    LIMITE_FREQUENCIA_HZ,
    LIMITE_TENSAO_V,
    Parametros,
    calcular_potencia,
    envelope,
    gerar_leitura,
    perfil_padrao,
)


def test_potencia_e_calculada_a_partir_de_tensao_corrente_e_fator():
    p = Parametros(tensao_volt=220.0, corrente_ampere=10.0, fator_potencia=0.9)

    assert p.potencia_watt == pytest.approx(1980.0)
    assert calcular_potencia(-1, 10, 0.9) == 0.0


def test_perfil_padrao_usa_prefixo_da_tag():
    assert perfil_padrao("inj-02").corrente_ampere == 32.0
    assert perfil_padrao("XYZ-01") == Parametros()


def test_perfil_padrao_devolve_copia_independente():
    perfil = perfil_padrao("CNC-01")
    perfil.corrente_ampere = 99

    assert perfil_padrao("CNC-01").corrente_ampere == 15.5


@pytest.mark.parametrize(
    ("t", "esperado"),
    [(0, 0.0), (1, 0.5), (5, 1.0), (9, 0.5), (10, 0.0), (11, 0.0)],
)
def test_envelope_sobe_mantem_e_desce(t, esperado):
    assert envelope(t, duracao=10, rampa=2) == pytest.approx(esperado)


def test_envelope_sem_rampa_mantem_intensidade_constante():
    assert envelope(1, duracao=10, rampa=0) == 1.0
    assert envelope(-1, duracao=10, rampa=0) == 0.0


def test_leitura_sem_ruido_reproduz_os_parametros():
    p = Parametros(tensao_volt=216.4, corrente_ampere=16.43, fator_potencia=0.85)

    leitura = gerar_leitura(1, p, "Ativa", ruido=False)

    assert leitura["tensao_volt"] == 216.4
    assert leitura["corrente_ampere"] == 16.43
    assert leitura["potencia_watt"] == pytest.approx(216.4 * 16.43 * 0.85, abs=0.1)
    assert leitura["status_atual"] == "Ativa"


@pytest.mark.parametrize("status", ["Desligada", "Manutenção"])
def test_maquina_parada_zera_corrente_vibracao_e_frequencia(status):
    leitura = gerar_leitura(1, Parametros(), status, ruido=False)

    assert leitura["corrente_ampere"] == 0.0
    assert leitura["vibracao_rms"] == 0.0
    assert leitura["frequencia_hz"] == 0.0
    assert leitura["potencia_watt"] == 0.0
    assert leitura["tensao_volt"] == 220.0


def test_leitura_respeita_limites_da_api():
    extremos = Parametros(tensao_volt=400, frequencia_hz=150, corrente_ampere=-5)

    leitura = gerar_leitura(1, extremos, "Ativa", ruido=False)

    assert leitura["tensao_volt"] == LIMITE_TENSAO_V
    assert leitura["frequencia_hz"] == LIMITE_FREQUENCIA_HZ
    assert leitura["corrente_ampere"] == 0.0


@pytest.mark.parametrize("status", ["Ativa", "Inativa", "Desligada", "Manutenção"])
@pytest.mark.parametrize("chave", list(CENARIOS))
def test_leituras_com_cenarios_sao_aceitas_pela_api(status, chave):
    """Toda leitura gerada precisa passar na validação de POST /enviar-dados."""
    rng = random.Random(42)
    cenario = CENARIOS[chave]

    for t in range(0, int(cenario.duracao_s), 5):
        parametros = cenario.aplicar(perfil_padrao("INJ-01"), t)
        LeituraSensor(**gerar_leitura(1, parametros, status, rng=rng))


def test_desgaste_de_rolamento_aumenta_vibracao_progressivamente():
    cenario = CENARIOS["desgaste_rolamento"]
    base = Parametros(vibracao_rms=2.0)

    inicio = cenario.aplicar(base, 0).vibracao_rms
    meio = cenario.aplicar(base, cenario.duracao_s / 2).vibracao_rms
    fim = cenario.aplicar(base, cenario.duracao_s).vibracao_rms

    assert inicio == pytest.approx(2.0)
    assert inicio < meio < fim
    assert fim == pytest.approx(7.0)


def test_sobrecarga_aumenta_corrente_no_pico():
    cenario = CENARIOS["sobrecarga"]

    pico = cenario.aplicar(Parametros(corrente_ampere=10), cenario.duracao_s / 2)

    assert pico.corrente_ampere == pytest.approx(14.0)


def test_queda_de_tensao_leva_a_190v():
    cenario = CENARIOS["queda_tensao"]

    pico = cenario.aplicar(Parametros(tensao_volt=220), cenario.duracao_s / 2)

    assert pico.tensao_volt == pytest.approx(190.0)


def test_cenario_nao_altera_os_parametros_originais():
    base = Parametros()

    CENARIOS["sobrecarga"].aplicar(base, 15)

    assert base == Parametros()


@pytest.mark.parametrize("chave", list(CENARIOS))
def test_intensidade_maior_produz_efeito_maior(chave):
    cenario = CENARIOS[chave]
    base = perfil_padrao("CNC-01")
    # Desgaste cresce até o fim; os outros têm o pico no meio
    fator = 0.9 if chave == "desgaste_rolamento" else 0.5
    t = cenario.duracao_s * fator

    def desvio(intensidade):
        p = cenario.aplicar(base, t, intensidade=intensidade)
        return sum(
            abs(getattr(p, campo) - getattr(base, campo)) / getattr(base, campo)
            for campo in ("tensao_volt", "corrente_ampere", "vibracao_rms")
        )

    assert desvio(0.5) < desvio(1.0) < desvio(1.5)


def test_duracao_personalizada_acelera_o_desgaste():
    cenario = CENARIOS["desgaste_rolamento"]
    base = Parametros(vibracao_rms=2.0)

    rapido = cenario.aplicar(base, 60, duracao_s=120).vibracao_rms
    padrao = cenario.aplicar(base, 60).vibracao_rms

    assert rapido > padrao
