import random

import pytest

from simulador.coleta import ColetaAutomatica, ConfigColeta
from simulador.estado import EstadoMaquina
from simulador.fisica import CENARIOS

CONFIG_RAPIDA = ConfigColeta(pausa_min_s=10, pausa_max_s=10)


def criar_maquina(id_=1, tag="CNC-01"):
    return EstadoMaquina.a_partir_da_api(
        {"id": id_, "tag_maquina": tag, "nome_maquina": tag, "setor": None}
    )


def test_coleta_inativa_nao_dispara_nada():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()

    assert coleta.passo([m], 0) == []
    assert coleta.passo([m], 100) == []
    assert m.cenario is None


def test_dispara_falha_depois_da_pausa_sorteada():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()
    coleta.iniciar(agora=0, sessao="teste")

    assert coleta.passo([m], 0) == []  # agenda a primeira falha para t=10
    assert coleta.passo([m], 5) == []  # ainda não chegou a hora
    disparos = coleta.passo([m], 10)

    assert disparos == [(1, m.cenario)]
    assert m.cenario in CENARIOS
    assert coleta.falhas_disparadas == 1


def test_falha_sorteia_intensidade_e_duracao_dentro_dos_limites():
    config = ConfigColeta(pausa_min_s=0, pausa_max_s=0)
    coleta = ColetaAutomatica(random.Random(7), config)
    coleta.iniciar(agora=0)
    intensidades, fatores = [], []

    for i in range(200):
        m = criar_maquina(i)
        coleta.passo([m], 0)
        coleta.passo([m], 0)
        ativo = m.cenario_ativo
        intensidades.append(ativo.intensidade)
        fatores.append(ativo.duracao_s / CENARIOS[ativo.chave].duracao_s)

    assert config.intensidade_min <= min(intensidades)
    assert max(intensidades) <= config.intensidade_max
    assert config.fator_duracao_min <= min(fatores)
    assert max(fatores) <= config.fator_duracao_max
    # Variação real, não sempre o mesmo valor
    assert max(intensidades) - min(intensidades) > 0.5
    assert len({m for m in fatores}) > 100


def test_todos_os_tipos_de_falha_sao_sorteados():
    coleta = ColetaAutomatica(
        random.Random(3), ConfigColeta(pausa_min_s=0, pausa_max_s=0)
    )
    coleta.iniciar(agora=0)
    sorteados = set()

    for i in range(100):
        m = criar_maquina(i)
        coleta.passo([m], 0)
        coleta.passo([m], 0)
        sorteados.add(m.cenario)

    assert sorteados == set(CENARIOS)


def test_nao_dispara_nova_falha_durante_outra():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()
    coleta.iniciar(agora=0)
    coleta.passo([m], 0)
    coleta.passo([m], 10)
    primeira = m.cenario_ativo

    coleta.passo([m], 11)
    coleta.passo([m], 30)

    assert m.cenario_ativo is primeira
    assert coleta.falhas_disparadas == 1


def test_proxima_falha_so_conta_apos_a_anterior_terminar():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()
    coleta.iniciar(agora=0)
    coleta.passo([m], 0)
    coleta.passo([m], 10)
    fim = 10 + m.cenario_ativo.duracao_s

    coleta.passo([m], fim)  # falha termina e a pausa de 10 s é agendada
    assert m.cenario is None
    assert coleta.passo([m], fim + 9) == []
    assert len(coleta.passo([m], fim + 10)) == 1


@pytest.mark.parametrize(
    "preparar",
    [
        lambda m: setattr(m, "em_manutencao", True),
        lambda m: setattr(m, "enviando", False),
        lambda m: setattr(m, "status", "Desligada"),
    ],
    ids=["em_manutencao", "pausada", "desligada"],
)
def test_nao_dispara_em_maquina_que_nao_pode_falhar(preparar):
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()
    preparar(m)
    coleta.iniciar(agora=0)

    for t in range(0, 100, 5):
        coleta.passo([m], t)

    assert m.cenario is None


def test_parar_interrompe_os_disparos():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    m = criar_maquina()
    coleta.iniciar(agora=0)
    coleta.passo([m], 0)

    coleta.parar()

    assert coleta.passo([m], 50) == []
    assert m.cenario is None


def test_iniciar_gera_nome_de_sessao_e_zera_contador():
    coleta = ColetaAutomatica(random.Random(1), CONFIG_RAPIDA)
    coleta.falhas_disparadas = 5

    coleta.iniciar(agora=0)

    assert coleta.sessao.startswith("coleta-")
    assert coleta.falhas_disparadas == 0
