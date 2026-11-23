import asyncio
import json
import random
from itertools import count

import pytest

from app import monitor as monitor_module
from app.monitor import (
    VOTOS_MINIMOS,
    Avaliacao,
    EstadoMaquina,
    MonitorFalhas,
    carregar_modelo,
    classificar_severidade,
    descrever,
)
from ml.features import LEITURAS_AQUECIMENTO, TAMANHO_HISTORICO
from simulador.estado import EstadoMaquina as MaquinaSimulada
from simulador.fisica import CENARIOS, gerar_leitura

# ---------- dublês ----------


class ArmazenamentoMemoria:
    def __init__(self, abertos=None, historicos=None, maquinas=(1,)):
        self.alertas = {}
        self.ids = count(1)
        self.abertos = abertos or []
        self.historicos = historicos or {}
        self.maquinas = list(maquinas)

    async def criar_alerta(self, dados):
        alerta = {"id": next(self.ids), "encerrado_em": None, **dados}
        self.alertas[alerta["id"]] = alerta
        return dict(alerta)

    async def atualizar_alerta(self, alerta_id, dados):
        self.alertas[alerta_id].update(dados)
        return dict(self.alertas[alerta_id])

    async def encerrar_alerta(self, alerta_id):
        self.alertas[alerta_id]["encerrado_em"] = "agora"
        return dict(self.alertas[alerta_id])

    async def listar_alertas_abertos(self):
        return self.abertos

    async def listar_maquinas(self):
        return self.maquinas

    async def leituras_recentes(self, maquina_id, limite):
        return self.historicos.get(maquina_id, [])[-limite:]


class ModeloFalso:
    """Detecta anomalia quando a vibração passa de 5; diagnóstico fixo."""

    leituras_confirmacao = 3
    limite_vibracao = 1.0
    metricas = {"deteccao": {"taxa_deteccao": 0.99}}
    treinado_em = "2026-11-17T00:00:00+00:00"
    versao_sklearn = "1.9.1"
    diagnostico = "sobrecarga"


def criar_monitor(armazenamento=None, **kwargs):
    eventos = []

    async def notificar(tipo, alerta):
        eventos.append((tipo, alerta))

    m = MonitorFalhas(armazenamento or ArmazenamentoMemoria(), notificar, **kwargs)
    return m, eventos


def leitura(vibracao=2.0, status="Ativa", maquina_id=1):
    return {
        "maquina_id": maquina_id,
        "status_atual": status,
        "tensao_volt": 220.0,
        "corrente_ampere": 15.0,
        "potencia_watt": 2805.0,
        "vibracao_rms": vibracao,
        "frequencia_hz": 60.0,
    }


def avaliacao_por_vibracao(historico):
    if len(historico) < 5:
        return None
    anomalo = historico[-1]["vibracao_rms"] > 5
    return Avaliacao(anomalo, 1.0 if anomalo else -1.0, "sobrecarga", 0.9, None)


@pytest.fixture
def monitor_falso(monkeypatch):
    m, eventos = criar_monitor(leituras_encerramento=4, intervalo_atualizacao=2)
    asyncio.run(m.iniciar(ModeloFalso()))
    monkeypatch.setattr(m, "avaliar", avaliacao_por_vibracao)
    return m, eventos


def processar(m, *leituras):
    async def rodar():
        for item in leituras:
            await m.processar(item)

    asyncio.run(rodar())


# ---------- regras do alerta (modelo falso) ----------


def test_sem_modelo_o_monitor_nao_faz_nada():
    m, eventos = criar_monitor()
    asyncio.run(m.iniciar(None))

    processar(m, leitura(vibracao=50))

    assert m.habilitado is False
    assert eventos == []
    status = m.status()
    assert status["habilitado"] is False
    assert status["maquinas"] == []
    assert "aviso" in status


def test_alerta_so_abre_apos_anomalias_seguidas(monitor_falso):
    m, eventos = monitor_falso
    processar(m, *[leitura() for _ in range(5)])

    processar(m, leitura(9), leitura(9))
    assert eventos == []

    processar(m, leitura(9))
    assert [tipo for tipo, _ in eventos] == ["alerta_criado"]
    # O começo da falha é ambíguo: o alerta nasce sem diagnóstico
    assert eventos[0][1]["diagnostico"] is None
    assert "em andamento" in eventos[0][1]["mensagem"]


def test_diagnostico_aparece_apos_votos_minimos(monkeypatch):
    m, eventos = criar_monitor(intervalo_atualizacao=1000)
    asyncio.run(m.iniciar(ModeloFalso()))
    monkeypatch.setattr(m, "avaliar", avaliacao_por_vibracao)
    processar(m, *[leitura() for _ in range(5)])
    processar(m, *[leitura(9) for _ in range(3)])  # abre com 1 voto

    processar(m, *[leitura(9) for _ in range(VOTOS_MINIMOS - 2)])
    assert [tipo for tipo, _ in eventos] == ["alerta_criado"]

    processar(m, leitura(9))
    tipo, alerta = eventos[-1]
    assert tipo == "alerta_atualizado"
    assert alerta["diagnostico"] == "sobrecarga"
    assert alerta["severidade"] == "alta"


def test_anomalia_interrompida_nao_abre_alerta(monitor_falso):
    m, eventos = monitor_falso
    processar(m, *[leitura() for _ in range(5)])

    processar(m, leitura(9), leitura(9), leitura(), leitura(9), leitura(9))

    assert eventos == []


def test_alerta_atualiza_e_encerra_quando_a_maquina_normaliza(monitor_falso):
    m, eventos = monitor_falso
    processar(m, *[leitura() for _ in range(5)])
    processar(m, *[leitura(9) for _ in range(5)])  # abre e atualiza

    processar(m, leitura(), leitura(), leitura())
    assert "alerta_encerrado" not in [tipo for tipo, _ in eventos]

    processar(m, leitura())
    tipos = [tipo for tipo, _ in eventos]
    assert tipos[0] == "alerta_criado"
    assert "alerta_atualizado" in tipos
    assert tipos[-1] == "alerta_encerrado"
    assert m.estados[1].alerta is None


def test_maquina_parada_encerra_alerta_e_nao_entra_no_historico(monitor_falso):
    m, eventos = monitor_falso
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(3)])
    tamanho = len(m.estados[1].historico)

    processar(m, leitura(status="Desligada"))

    assert eventos[-1][0] == "alerta_encerrado"
    assert len(m.estados[1].historico) == tamanho


def test_erro_no_modelo_nao_propaga(monitor_falso, monkeypatch, capsys):
    m, _ = monitor_falso

    def quebrar(historico):
        raise RuntimeError("modelo quebrado")

    monkeypatch.setattr(m, "avaliar", quebrar)

    processar(m, leitura())  # não pode levantar exceção

    assert "modelo quebrado" in capsys.readouterr().out


def test_iniciar_recupera_alertas_abertos_e_historico():
    historico = [leitura() for _ in range(TAMANHO_HISTORICO + 50)]
    armazenamento = ArmazenamentoMemoria(
        abertos=[
            {"id": 7, "maquina_id": 2, "diagnostico": "sobrecarga", "pontuacao": 0.3}
        ],
        historicos={1: historico},
        maquinas=(1, 2),
    )
    m, _ = criar_monitor(armazenamento)

    asyncio.run(m.iniciar(ModeloFalso()))

    assert len(m.estados[1].historico) == TAMANHO_HISTORICO
    assert m.estados[2].alerta["id"] == 7
    # O diagnóstico do alerta recuperado continua visível
    assert m.estados[2].diagnostico_atual()[0] == "sobrecarga"
    status = {s["maquina_id"]: s for s in m.status()["maquinas"]}
    assert status[1]["aquecida"] is True
    assert status[2]["alerta_aberto_id"] == 7
    assert m.status()["modelo"]["taxa_deteccao"] == 0.99


# ---------- fila de processamento ----------


def test_agendar_nao_bloqueia_e_mantem_a_ordem(monitor_falso):
    m, _ = monitor_falso

    async def rodar():
        for vibracao in (1.0, 2.0, 3.0):
            m.agendar(leitura(vibracao))
        # Devolve o controle na hora: a requisição não espera o ML
        assert len(m.estados.get(1, EstadoMaquina(historico=[])).historico) == 0
        await asyncio.gather(*m._tarefas)

    asyncio.run(rodar())

    assert [i["vibracao_rms"] for i in m.estados[1].historico] == [1.0, 2.0, 3.0]
    assert not m._tarefas


def test_agendar_sem_modelo_nao_cria_tarefa():
    m, _ = criar_monitor()

    async def rodar():
        await m.iniciar(None)
        m.agendar(leitura())
        assert not m._tarefas

    asyncio.run(rodar())


def test_parar_cancela_a_fila(monitor_falso, monkeypatch):
    m, eventos = monitor_falso

    async def travar(*_):
        await asyncio.Event().wait()

    monkeypatch.setattr(m, "processar", travar)

    async def rodar():
        m.agendar(leitura())
        await asyncio.sleep(0)
        await m.parar()
        await asyncio.sleep(0)
        assert not m._tarefas

    asyncio.run(rodar())
    assert eventos == []


# ---------- linha de base congelada ----------

BASE = {
    "tensao_volt": 220.0,
    "corrente_ampere": 15.0,
    "potencia_watt": 2805.0,
    "vibracao_rms": 2.0,
    "frequencia_hz": 60.0,
}


@pytest.fixture
def monitor_com_base(monkeypatch):
    m, eventos = criar_monitor(leituras_encerramento=4, intervalo_atualizacao=2)
    asyncio.run(m.iniciar(ModeloFalso()))
    bases_usadas = []

    def avaliar(historico, base=None):
        bases_usadas.append(base)
        return avaliacao_por_vibracao(historico)

    monkeypatch.setattr(m, "avaliar", avaliar)
    monkeypatch.setattr(m, "_linha_de_base", lambda historico: dict(BASE))
    return m, eventos, bases_usadas


def test_alerta_congela_a_base_e_a_grava(monitor_com_base):
    m, eventos, bases = monitor_com_base
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(3)])
    assert bases[-1] is None

    processar(m, leitura(9))

    assert bases[-1] == BASE
    assert eventos[0][1]["linha_de_base"] == BASE


def test_encerrar_tira_a_falha_do_historico(monitor_com_base, monkeypatch):
    m, _, _ = monitor_com_base
    monkeypatch.setattr(monitor_module, "JANELA_TENDENCIA", 3)
    processar(m, *[leitura() for _ in range(100)], *[leitura(9) for _ in range(30)])

    processar(m, *[leitura() for _ in range(4)])

    estado = m.estados[1]
    assert estado.alerta is None
    assert estado.base_congelada is None
    assert all(item["vibracao_rms"] == 2.0 for item in estado.historico)


def test_alerta_nao_encerra_com_sinal_fora_da_faixa(monitor_com_base, monkeypatch):
    m, eventos, _ = monitor_com_base

    def avaliar(historico, base=None):
        vibracao = historico[-1]["vibracao_rms"]
        anomalo = vibracao > 5
        return Avaliacao(
            anomalo,
            1.0 if anomalo else -1.0,
            "sobrecarga",
            0.9,
            None,
            fora_da_faixa=base is not None and vibracao > 3,
        )

    monkeypatch.setattr(m, "avaliar", avaliar)
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(3)])

    # O detector não vê anomalia, mas a vibração segue acima da faixa
    processar(m, *[leitura(4) for _ in range(20)])
    assert m.estados[1].alerta is not None

    processar(m, *[leitura() for _ in range(4)])
    assert m.estados[1].alerta is None
    assert eventos[-1][0] == "alerta_encerrado"


def test_manutencao_encerra_alerta_e_reinicia_o_historico(monitor_com_base):
    m, eventos, _ = monitor_com_base
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(3)])

    processar(m, leitura(status="Manutenção"))

    assert eventos[-1][0] == "alerta_encerrado"
    assert len(m.estados[1].historico) == 0
    assert m.estados[1].base_congelada is None


def test_reiniciar_ao_concluir_manutencao(monitor_com_base):
    m, eventos, _ = monitor_com_base
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(3)])

    asyncio.run(m.reiniciar_linha_de_base(1))

    assert eventos[-1][0] == "alerta_encerrado"
    assert len(m.estados[1].historico) == 0


def test_rejeicao_de_outro_diagnostico_nao_reinicia(monitor_com_base):
    m, eventos, _ = monitor_com_base
    processar(m, *[leitura() for _ in range(5)], *[leitura(9) for _ in range(8)])
    assert m.estados[1].alerta["diagnostico"] == "sobrecarga"

    asyncio.run(m.reiniciar_linha_de_base(1, apenas_diagnostico="queda_tensao"))
    assert m.estados[1].alerta is not None

    asyncio.run(m.reiniciar_linha_de_base(1, apenas_diagnostico="sobrecarga"))
    assert m.estados[1].alerta is None
    assert eventos[-1][0] == "alerta_encerrado"


def test_reiniciar_maquina_desconhecida_nao_faz_nada(monitor_com_base):
    m, eventos, _ = monitor_com_base

    asyncio.run(m.reiniciar_linha_de_base(99))

    assert eventos == []


def test_iniciar_recupera_a_base_gravada_como_texto():
    armazenamento = ArmazenamentoMemoria(
        abertos=[
            {
                "id": 7,
                "maquina_id": 1,
                "diagnostico": "sobrecarga",
                "pontuacao": 0.3,
                "linha_de_base": json.dumps(BASE),
            }
        ],
    )
    m, _ = criar_monitor(armazenamento)

    asyncio.run(m.iniciar(ModeloFalso()))

    assert m.estados[1].base_congelada == BASE


def avaliacao_desgaste(minutos):
    return Avaliacao(True, 1.0, "desgaste_rolamento", 0.9, minutos)


def estado_com_desgaste():
    estado = EstadoMaquina(historico=[])
    for _ in range(VOTOS_MINIMOS):
        estado.votacao.votar("desgaste_rolamento", 1.0)
    estado.leituras_anomalas_no_alerta = VOTOS_MINIMOS
    return estado


def test_severidade_nunca_diminui_com_o_alerta_aberto():
    estado = estado_com_desgaste()

    alta = MonitorFalhas._dados_alerta(1, estado, avaliacao_desgaste(1.0))
    depois = MonitorFalhas._dados_alerta(1, estado, avaliacao_desgaste(30.0))

    assert alta["severidade"] == "alta"
    assert depois["severidade"] == "alta"


def test_limite_atingido_continua_na_mensagem_depois():
    estado = estado_com_desgaste()

    MonitorFalhas._dados_alerta(1, estado, avaliacao_desgaste(0.0))
    # Na transição a vibração cai e a regressão não vê mais tendência de alta
    depois = MonitorFalhas._dados_alerta(1, estado, avaliacao_desgaste(None))

    assert depois["minutos_ate_limite"] == 0.0
    assert "já passou do limite" in depois["mensagem"]


@pytest.mark.parametrize(
    ("diagnostico", "minutos", "esperado"),
    [
        ("sobrecarga", None, "alta"),
        ("queda_tensao", None, "alta"),
        ("desbalanceamento", None, "media"),
        ("desgaste_rolamento", None, "media"),
        ("desgaste_rolamento", 10.0, "media"),
        ("desgaste_rolamento", 1.5, "alta"),
        (None, None, "media"),
    ],
)
def test_severidade(diagnostico, minutos, esperado):
    assert classificar_severidade(diagnostico, minutos) == esperado


def test_mensagens():
    assert "fora do padrão" in descrever(None, None, None)
    assert "sobrecarga (confiança de 90%)" in descrever("sobrecarga", 0.9, None)
    assert "~3 min" in descrever("desgaste_rolamento", 1.0, 3.2)
    assert "já passou do limite" in descrever("desgaste_rolamento", 1.0, 0.0)
    assert "menos de 1 min" in descrever("desgaste_rolamento", 1.0, 0.4)


def test_carregar_modelo_inexistente_desliga_o_monitor(tmp_path, capsys):
    assert carregar_modelo(tmp_path / "nao_existe.joblib") is None
    assert "desligado" in capsys.readouterr().out


def test_carregar_modelo_desligado_por_variavel(monkeypatch):
    monkeypatch.setattr(monitor_module, "ML_HABILITADO", False)

    assert carregar_modelo() is None


# ---------- ponta a ponta com o modelo treinado ----------


def operar(m, maquina, segundos, rng, relogio):
    """Gera leituras do simulador e passa pelo monitor, como a API faria."""

    async def rodar():
        for _ in range(int(segundos / 2)):
            relogio[0] += 2
            parametros = maquina.parametros_efetivos(relogio[0])
            await m.processar(gerar_leitura(maquina.id, parametros, "Ativa", rng=rng))

    asyncio.run(rodar())


@pytest.fixture(scope="module")
def modelo_real():
    modelo = carregar_modelo()
    if modelo is None:
        pytest.skip("modelo treinado não encontrado em ml/modelos/")
    return modelo


@pytest.mark.parametrize("chave", list(CENARIOS))
def test_modelo_real_detecta_diagnostica_e_encerra(modelo_real, chave):
    m, eventos = criar_monitor()
    asyncio.run(m.iniciar(modelo_real))
    maquina = MaquinaSimulada.a_partir_da_api(
        {"id": 1, "tag_maquina": "INJ-01", "nome_maquina": "Injetora", "setor": None}
    )
    rng, relogio = random.Random(5), [0.0]

    # Operação normal até aquecer a linha de base, sem nenhum alerta
    operar(m, maquina, LEITURAS_AQUECIMENTO * 2 + 120, rng, relogio)
    assert eventos == []

    maquina.iniciar_cenario(chave, relogio[0])
    operar(m, maquina, CENARIOS[chave].duracao_s, rng, relogio)
    criados = [alerta for tipo, alerta in eventos if tipo == "alerta_criado"]
    assert len(criados) == 1

    # Volta ao normal: o alerta encerra (3 min de transição + 3 min normais)
    operar(m, maquina, 420, rng, relogio)
    finais = [alerta for tipo, alerta in eventos if tipo == "alerta_encerrado"]
    assert len(finais) == 1
    assert finais[0]["diagnostico"] == chave
    assert finais[0]["mensagem"]
    if chave == "desgaste_rolamento":
        # Durante o desgaste a regressão estimou quando a vibração chega ao limite
        previsoes = [
            alerta["minutos_ate_limite"]
            for tipo, alerta in eventos
            if tipo in ("alerta_criado", "alerta_atualizado")
        ]
        assert any(minutos is not None for minutos in previsoes)
