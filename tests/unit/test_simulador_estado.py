import csv
import random

import pytest

from simulador.cliente_api import ResultadoEnvio
from simulador.estado import EstadoMaquina, Simulador
from simulador.fisica import CENARIOS, perfil_padrao
from simulador.rotulos import COLUNAS, GravadorRotulos


class ClienteFalso:
    def __init__(self, maquinas=None, resultado=ResultadoEnvio.ENVIADO):
        self.maquinas = maquinas
        self.resultado = resultado
        self.enviadas = []

    async def listar_maquinas(self):
        return self.maquinas

    async def enviar(self, leitura):
        self.enviadas.append(leitura)
        return self.resultado


class Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora


def maquina_api(id_=1, tag="CNC-01", em_manutencao=False):
    return {
        "id": id_,
        "tag_maquina": tag,
        "nome_maquina": f"Máquina {tag}",
        "setor": "Usinagem",
        "em_manutencao": em_manutencao,
    }


def criar_simulador(cliente, gravador=None, relogio=None):
    return Simulador(
        cliente,
        gravador,
        intervalo_envio_s=2,
        intervalo_sincronizacao_s=15,
        rng=random.Random(1),
        relogio=relogio or Relogio(),
    )


# ---------- EstadoMaquina ----------


def test_maquina_criada_com_perfil_da_tag():
    m = EstadoMaquina.a_partir_da_api(maquina_api(tag="INJ-01"))

    assert m.parametros == perfil_padrao("INJ-01")
    assert m.rotulo() == "normal"
    assert m.parametros_alterados is False


def test_cenario_termina_sozinho_apos_a_duracao():
    m = EstadoMaquina.a_partir_da_api(maquina_api())
    m.iniciar_cenario("sobrecarga", agora=0)

    assert m.rotulo() == "sobrecarga"
    assert m.progresso_cenario(15) == pytest.approx(0.5)

    m.atualizar_cenario(CENARIOS["sobrecarga"].duracao_s)

    assert m.cenario is None
    assert m.rotulo() == "normal"


def test_cenario_desconhecido_e_recusado():
    m = EstadoMaquina.a_partir_da_api(maquina_api())

    with pytest.raises(ValueError):
        m.iniciar_cenario("explosao", agora=0)


def test_manutencao_tem_prioridade_sobre_o_status_escolhido():
    m = EstadoMaquina.a_partir_da_api(maquina_api(em_manutencao=True))
    m.status = "Ativa"

    assert m.status_efetivo(0, random.Random()) == "Manutenção"
    assert m.rotulo() == "manutencao"


def test_modo_automatico_mantem_o_status_ate_o_prazo():
    m = EstadoMaquina.a_partir_da_api(maquina_api())
    m.modo_automatico = True
    rng = random.Random(3)

    primeiro = m.status_efetivo(0, rng)

    assert m.status_efetivo(1, rng) == primeiro
    assert primeiro in ("Ativa", "Inativa", "Desligada")


def test_restaurar_perfil_preserva_o_objeto_ligado_aos_sliders():
    m = EstadoMaquina.a_partir_da_api(maquina_api())
    parametros = m.parametros
    parametros.corrente_ampere = 50

    assert m.parametros_alterados is True

    m.restaurar_perfil()

    assert m.parametros is parametros
    assert m.parametros_alterados is False


# ---------- Simulador ----------


@pytest.mark.asyncio
async def test_sincronizar_adiciona_atualiza_e_remove_maquinas():
    cliente = ClienteFalso([maquina_api(1, "CNC-01"), maquina_api(2, "INJ-01")])
    sim = criar_simulador(cliente)

    assert await sim.sincronizar_maquinas() is True
    assert set(sim.maquinas) == {1, 2}

    sim.maquinas[1].parametros.corrente_ampere = 42
    cliente.maquinas = [maquina_api(1, "CNC-01", em_manutencao=True)]
    await sim.sincronizar_maquinas()

    assert set(sim.maquinas) == {1}
    assert sim.maquinas[1].em_manutencao is True
    # Ajustes feitos no painel sobrevivem à sincronização
    assert sim.maquinas[1].parametros.corrente_ampere == 42


@pytest.mark.asyncio
async def test_sincronizar_sem_api_mantem_maquinas():
    cliente = ClienteFalso([maquina_api()])
    sim = criar_simulador(cliente)
    await sim.sincronizar_maquinas()

    cliente.maquinas = None

    assert await sim.sincronizar_maquinas() is False
    assert set(sim.maquinas) == {1}


@pytest.mark.asyncio
async def test_ciclo_envia_apenas_maquinas_ativas_no_painel():
    cliente = ClienteFalso([maquina_api(1, "CNC-01"), maquina_api(2, "INJ-01")])
    sim = criar_simulador(cliente)
    await sim.sincronizar_maquinas()
    sim.maquinas[2].enviando = False

    await sim.ciclo()

    assert [leitura["maquina_id"] for leitura in cliente.enviadas] == [1]
    assert sim.maquinas[1].ultima_leitura is not None
    assert len(sim.maquinas[1].historico) == 1


@pytest.mark.asyncio
async def test_envio_grava_rotulo_verdadeiro_sem_enviar_para_a_api(tmp_path):
    arquivo = tmp_path / "rotulos.csv"
    cliente = ClienteFalso([maquina_api()])
    relogio = Relogio()
    sim = criar_simulador(cliente, GravadorRotulos(arquivo), relogio)
    await sim.sincronizar_maquinas()
    maquina = sim.maquinas[1]

    await sim.enviar_maquina(maquina)
    maquina.iniciar_cenario("desgaste_rolamento", relogio.agora)
    relogio.agora += 150
    await sim.enviar_maquina(maquina)

    with arquivo.open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))

    assert tuple(linhas[0]) == COLUNAS
    assert [linha["cenario"] for linha in linhas] == ["normal", "desgaste_rolamento"]
    assert linhas[1]["resultado_envio"] == "enviado"
    # O rótulo nunca vai no payload enviado à API
    assert all("cenario" not in leitura for leitura in cliente.enviadas)
    # A falha aparece nos dados: vibração acima da nominal
    assert float(linhas[1]["vibracao_rms"]) > perfil_padrao("CNC-01").vibracao_rms
