"""Monitor de falhas: aplica os modelos de ML a cada leitura recebida.

Fluxo por máquina, a cada leitura de POST /enviar-dados (em segundo plano,
depois que a leitura já foi gravada e transmitida):

1. guarda a leitura no histórico da máquina (só com a máquina 'Ativa');
2. calcula as features com o MESMO código do treino (ml/features.py);
3. o detector diz se está fora do padrão; a árvore diz que falha parece ser;
4. abre, diagnostica e encerra o alerta com as MESMAS regras usadas na
   avaliação offline (ml/alertas.py);
5. cada mudança é gravada no banco e enviada pelo WebSocket /ws/alertas.

Se o modelo não puder ser carregado, o monitor fica desligado e a API segue
funcionando normalmente: a telemetria nunca depende do ML.
"""

import asyncio
import json
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app import repository
from ml.alertas import LEITURAS_ENCERRAMENTO, VotacaoDiagnostico
from ml.features import (
    JANELA_TENDENCIA,
    LEITURAS_AQUECIMENTO,
    SINAIS,
    TAMANHO_HISTORICO,
)

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_MODELO = Path(
    os.getenv("ML_MODELO_PATH", RAIZ / "ml" / "modelos" / "modelo_falhas.joblib")
)
ML_HABILITADO = os.getenv("ML_HABILITADO", "true").strip().lower() not in {
    "0",
    "false",
    "nao",
    "não",
    "no",
}

# Com o alerta aberto, regrava o diagnóstico no banco a cada N leituras anômalas
INTERVALO_ATUALIZACAO = 15
# Desgaste com previsão de atingir o limite em até N minutos é severidade alta
MINUTOS_CRITICOS = 2.0
# Leituras anômalas antes de mostrar um diagnóstico (10 s). O começo de uma falha
# é a parte mais ambígua; diagnosticar com 1 leitura gerava trocas de diagnóstico.
VOTOS_MINIMOS = 5

ORDEM_SEVERIDADE = {"baixa": 0, "media": 1, "alta": 2}

NOMES_FALHAS = {
    "desgaste_rolamento": "desgaste de rolamento",
    "sobrecarga": "sobrecarga",
    "queda_tensao": "queda de tensão",
    "desbalanceamento": "desbalanceamento",
}
# Falhas elétricas podem danificar o motor rapidamente
FALHAS_ALTA_SEVERIDADE = {"sobrecarga", "queda_tensao"}
# Serviço sugerido na solicitação de manutenção preditiva
ACOES_MANUTENCAO = {
    "desgaste_rolamento": "Inspecionar e lubrificar os rolamentos; trocar se necessário.",
    "sobrecarga": "Verificar a carga mecânica, a corrente do motor e a proteção térmica.",
    "queda_tensao": "Verificar a alimentação elétrica, os cabos e as conexões.",
    "desbalanceamento": "Verificar o balanceamento, o alinhamento e a fixação do conjunto.",
}


@dataclass(frozen=True)
class Avaliacao:
    anomalo: bool
    pontuacao: float
    diagnostico: str
    probabilidade: float
    minutos_ate_limite: float | None
    # Com o alerta aberto: algum sinal segue fora da faixa da referência
    fora_da_faixa: bool = False


@dataclass
class EstadoMaquina:
    historico: deque
    anomalias_seguidas: int = 0
    normais_seguidas: int = 0
    alerta: dict | None = None
    votacao: VotacaoDiagnostico = field(default_factory=VotacaoDiagnostico)
    pontuacao_maxima: float = 0.0
    leituras_anomalas_no_alerta: int = 0
    # A severidade nunca diminui enquanto o alerta está aberto
    severidade_maxima: str = "baixa"
    # O desgaste já levou a vibração ao limite neste alerta
    limite_atingido: bool = False
    ultima_avaliacao: Avaliacao | None = None
    # Referência congelada enquanto o alerta está aberto
    base_congelada: dict[str, float] | None = None
    # Leituras anteriores à falha, que voltam ao histórico quando o alerta encerra
    historico_limpo: list[dict] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def limpar_alerta(self) -> None:
        self.alerta = None
        self.base_congelada = None
        self.historico_limpo = None
        self.votacao = VotacaoDiagnostico()
        self.pontuacao_maxima = 0.0
        self.leituras_anomalas_no_alerta = 0
        self.severidade_maxima = "baixa"
        self.limite_atingido = False

    def diagnostico_atual(self) -> tuple[str | None, float | None]:
        """Diagnóstico exibido: só depois de VOTOS_MINIMOS leituras anômalas."""
        if self.leituras_anomalas_no_alerta < VOTOS_MINIMOS:
            return None, None
        return self.votacao.resultado()


class Armazenamento(Protocol):
    async def criar_alerta(self, dados: dict) -> dict | None: ...
    async def atualizar_alerta(self, alerta_id: int, dados: dict) -> dict | None: ...
    async def encerrar_alerta(self, alerta_id: int) -> dict | None: ...
    async def listar_alertas_abertos(self) -> list[dict]: ...
    async def listar_maquinas(self) -> list[int]: ...
    async def leituras_recentes(self, maquina_id: int, limite: int) -> list[dict]: ...


def classificar_severidade(diagnostico: str | None, minutos: float | None) -> str:
    if diagnostico in FALHAS_ALTA_SEVERIDADE:
        return "alta"
    if diagnostico == "desgaste_rolamento" and minutos is not None:
        return "alta" if minutos <= MINUTOS_CRITICOS else "media"
    return "media"


def descrever(
    diagnostico: str | None, confianca: float | None, minutos: float | None
) -> str:
    if not diagnostico:
        return "Comportamento fora do padrão da máquina. Diagnóstico em andamento."
    texto = f"Provável {NOMES_FALHAS.get(diagnostico, diagnostico)}"
    if confianca is not None:
        texto += f" (confiança de {confianca:.0%})"
    texto += "."
    if diagnostico == "desgaste_rolamento" and minutos is not None:
        if minutos <= 0:
            texto += " A vibração já passou do limite (2× o normal)."
        elif minutos < 1:
            texto += (
                " A vibração deve chegar ao limite (2× o normal) em menos de 1 min."
            )
        else:
            texto += f" A vibração deve chegar ao limite (2× o normal) em ~{minutos:.0f} min."
    return texto


# Problema encontrado na última tentativa de carregar o modelo
aviso_modelo: str | None = None


def descrever_manutencao(diagnostico: str | None) -> str | None:
    """Serviço proposto ao analista. None enquanto não há diagnóstico."""
    if diagnostico not in ACOES_MANUTENCAO:
        return None
    return (
        f"Manutenção preditiva por provável {NOMES_FALHAS[diagnostico]}: "
        f"{ACOES_MANUTENCAO[diagnostico]}"
    )


def carregar_modelo(caminho: Path = CAMINHO_MODELO):
    """Carrega o ModeloFalhas, ou retorna None se não der.

    O motivo de um desligamento, ou de uma versão incompatível, fica em
    `aviso_modelo` e aparece em GET /ml/status.
    """
    global aviso_modelo
    aviso_modelo = None
    if not ML_HABILITADO:
        aviso_modelo = "Monitor de ML desligado (ML_HABILITADO=false)"
        print(f"--- {aviso_modelo} ---")
        return None
    try:
        import sklearn

        from ml.modelo import ModeloFalhas

        modelo = ModeloFalhas.carregar(caminho)
        print(f"--- Modelo de ML carregado (treinado em {modelo.treinado_em}) ---")
        if modelo.versao_sklearn != sklearn.__version__:
            aviso_modelo = (
                f"Modelo treinado com scikit-learn {modelo.versao_sklearn}, mas a API"
                f" usa {sklearn.__version__}. Retreine com python -m ml.treinar."
            )
            print(f"--- AVISO: {aviso_modelo} ---")
        return modelo
    except Exception as erro:
        aviso_modelo = f"Monitor de ML desligado: modelo não carregado ({erro})"
        print(f"--- ERRO: {aviso_modelo} ---")
        return None


class MonitorFalhas:
    def __init__(
        self,
        armazenamento: Armazenamento,
        notificar: Callable[[str, dict], Awaitable[None]],
        leituras_encerramento: int = LEITURAS_ENCERRAMENTO,
        intervalo_atualizacao: int = INTERVALO_ATUALIZACAO,
    ):
        self.armazenamento = armazenamento
        self.notificar = notificar
        self.leituras_encerramento = leituras_encerramento
        self.intervalo_atualizacao = intervalo_atualizacao
        self.modelo = None
        self.estados: dict[int, EstadoMaquina] = {}
        self._tarefas: set[asyncio.Task] = set()

    @property
    def habilitado(self) -> bool:
        return self.modelo is not None

    def _estado(self, maquina_id: int) -> EstadoMaquina:
        if maquina_id not in self.estados:
            self.estados[maquina_id] = EstadoMaquina(
                historico=deque(maxlen=TAMANHO_HISTORICO)
            )
        return self.estados[maquina_id]

    async def iniciar(self, modelo) -> None:
        """Recupera alertas abertos e o histórico recente, para não começar às cegas."""
        self.modelo = modelo
        self.estados.clear()
        if not self.habilitado:
            return

        for alerta in await self.armazenamento.listar_alertas_abertos():
            estado = self._estado(alerta["maquina_id"])
            estado.alerta = alerta
            estado.pontuacao_maxima = alerta.get("pontuacao") or 0.0
            estado.severidade_maxima = alerta.get("severidade") or "baixa"
            estado.limite_atingido = alerta.get("minutos_ate_limite") == 0
            if alerta.get("diagnostico"):
                # O diagnóstico já gravado entra como voto inicial e continua visível
                estado.votacao.votar(
                    alerta["diagnostico"], max(estado.pontuacao_maxima, 1e-6)
                )
                estado.leituras_anomalas_no_alerta = VOTOS_MINIMOS

        for maquina_id in await self.armazenamento.listar_maquinas():
            leituras = await self.armazenamento.leituras_recentes(
                maquina_id, TAMANHO_HISTORICO
            )
            self._estado(maquina_id).historico.extend(leituras)

        for estado in self.estados.values():
            if estado.alerta:
                historico = list(estado.historico)
                base = estado.alerta.get("linha_de_base")
                # O asyncpg devolve jsonb como texto
                base = json.loads(base) if isinstance(base, str) else base
                estado.base_congelada = base or self._linha_de_base(historico)
                if estado.base_congelada:
                    estado.historico_limpo = historico

    # ---------- avaliação (CPU, roda numa thread) ----------

    @staticmethod
    def _linha_de_base(historico: list[dict]) -> dict[str, float] | None:
        if len(historico) < LEITURAS_AQUECIMENTO:
            return None

        import pandas as pd

        from ml.features import linhas_de_base_atuais

        return linhas_de_base_atuais(pd.DataFrame(historico, columns=list(SINAIS)))

    def avaliar(
        self, historico: list[dict], base_fixa: dict[str, float] | None = None
    ) -> Avaliacao | None:
        import pandas as pd

        from ml.alertas import fora_da_faixa
        from ml.features import calcular_features, vibracao_relativa
        from ml.tendencia import JANELA_PADRAO, minutos_ate_limite

        leituras = pd.DataFrame(historico, columns=list(SINAIS))
        features = calcular_features(leituras, base_fixa).iloc[[-1]]
        if features.isna().any(axis=None):
            return None

        pontuacao = float(self.modelo.pontuacao_anomalia(features)[0])
        classes, probabilidades = self.modelo.diagnosticar(features)
        diagnostico = str(classes[0])

        minutos = None
        if diagnostico == "desgaste_rolamento":
            serie = vibracao_relativa(leituras, base_fixa).to_numpy()[-JANELA_PADRAO:]
            minutos = minutos_ate_limite(serie, self.modelo.limite_vibracao)

        return Avaliacao(
            anomalo=pontuacao > 0,
            pontuacao=pontuacao,
            diagnostico=diagnostico,
            probabilidade=float(probabilidades[0]),
            minutos_ate_limite=minutos,
            fora_da_faixa=base_fixa is not None and bool(fora_da_faixa(features)[0]),
        )

    # ---------- processamento de cada leitura ----------

    def agendar(self, leitura: dict) -> None:
        """Processa a leitura sem prender a requisição nem sua conexão do banco."""
        if not self.habilitado:
            return
        tarefa = asyncio.create_task(self.processar(leitura))
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)

    async def parar(self) -> None:
        """Cancela as leituras na fila antes de o pool de conexões fechar."""
        tarefas = list(self._tarefas)
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)

    async def processar(self, leitura: dict) -> None:
        """Nunca levanta exceção: um erro no ML não pode afetar a telemetria."""
        if not self.habilitado:
            return
        try:
            estado = self._estado(leitura["maquina_id"])
            async with estado.lock:
                await self._processar(leitura["maquina_id"], estado, leitura)
        except Exception as erro:
            print(
                f"Erro no monitor de ML (máquina {leitura.get('maquina_id')}): {erro}"
            )

    async def reiniciar_linha_de_base(
        self, maquina_id: int, apenas_diagnostico: str | None = None
    ) -> None:
        """Esquece a referência da máquina depois de uma intervenção humana.

        Com `apenas_diagnostico`, só age se o alerta aberto tem esse diagnóstico
        (usado quando a solicitação é rejeitada: o nível atual é o novo normal).
        Nunca levanta exceção: a ação do usuário já foi gravada.
        """
        if not self.habilitado or maquina_id not in self.estados:
            return
        estado = self.estados[maquina_id]
        try:
            async with estado.lock:
                if apenas_diagnostico is not None and (
                    not estado.alerta
                    or estado.alerta.get("diagnostico") != apenas_diagnostico
                ):
                    return
                await self._reiniciar(estado)
        except Exception as erro:
            print(f"Erro ao reiniciar a linha de base da máquina {maquina_id}: {erro}")

    async def _reiniciar(self, estado: EstadoMaquina) -> None:
        estado.anomalias_seguidas = estado.normais_seguidas = 0
        if estado.alerta:
            await self._encerrar(estado, manter_recentes=0)
        estado.historico.clear()
        estado.ultima_avaliacao = None

    async def _processar(self, maquina_id: int, estado: EstadoMaquina, leitura: dict):
        status_atual = leitura.get("status_atual")
        if status_atual == "Manutenção":
            # Depois do serviço, o comportamento saudável pode ser outro
            await self._reiniciar(estado)
            return
        if status_atual != "Ativa":
            # Máquina parada: não há comportamento a avaliar
            estado.anomalias_seguidas = estado.normais_seguidas = 0
            if estado.alerta:
                await self._encerrar(estado, manter_recentes=0)
            return

        estado.historico.append({sinal: float(leitura[sinal]) for sinal in SINAIS})
        historico = list(estado.historico)
        if estado.base_congelada is None:
            avaliacao = await asyncio.to_thread(self.avaliar, historico)
        else:
            avaliacao = await asyncio.to_thread(
                self.avaliar, historico, estado.base_congelada
            )
        estado.ultima_avaliacao = avaliacao
        if avaliacao is None:  # ainda aquecendo a linha de base
            return

        if avaliacao.anomalo:
            estado.anomalias_seguidas += 1
            estado.normais_seguidas = 0
        elif avaliacao.fora_da_faixa:
            estado.anomalias_seguidas = estado.normais_seguidas = 0
        else:
            estado.normais_seguidas += 1
            estado.anomalias_seguidas = 0

        if estado.alerta is None:
            if estado.anomalias_seguidas >= self.modelo.leituras_confirmacao:
                await self._abrir(maquina_id, estado, avaliacao)
            return

        if avaliacao.anomalo:
            antes = estado.diagnostico_atual()[0]
            self._votar(estado, avaliacao)
            mudou = estado.diagnostico_atual()[0] != antes
            periodico = (
                estado.leituras_anomalas_no_alerta % self.intervalo_atualizacao == 0
            )
            if mudou or periodico:
                await self._atualizar(maquina_id, estado, avaliacao)
        elif estado.normais_seguidas >= self.leituras_encerramento:
            await self._encerrar(estado)

    # ---------- ciclo de vida do alerta ----------

    @staticmethod
    def _votar(estado: EstadoMaquina, avaliacao: Avaliacao) -> None:
        estado.votacao.votar(avaliacao.diagnostico, avaliacao.pontuacao)
        estado.leituras_anomalas_no_alerta += 1
        estado.pontuacao_maxima = max(estado.pontuacao_maxima, avaliacao.pontuacao)

    @staticmethod
    def _dados_alerta(maquina_id: int, estado: EstadoMaquina, avaliacao: Avaliacao):
        diagnostico, confianca = estado.diagnostico_atual()
        minutos = None
        if diagnostico == "desgaste_rolamento":
            minutos = avaliacao.minutos_ate_limite
            if minutos is not None and minutos <= 0:
                estado.limite_atingido = True
            elif minutos is None and estado.limite_atingido:
                minutos = 0.0  # já passou do limite; a vibração só está caindo agora

        severidade = max(
            estado.severidade_maxima,
            classificar_severidade(diagnostico, minutos),
            key=ORDEM_SEVERIDADE.get,
        )
        estado.severidade_maxima = severidade
        return {
            "maquina_id": maquina_id,
            "diagnostico": diagnostico,
            "confianca": None if confianca is None else round(confianca, 3),
            "pontuacao": round(estado.pontuacao_maxima, 4),
            "severidade": severidade,
            "mensagem": descrever(diagnostico, confianca, minutos),
            "minutos_ate_limite": None if minutos is None else round(minutos, 1),
            "manutencao_descricao": descrever_manutencao(diagnostico),
        }

    async def _abrir(self, maquina_id: int, estado: EstadoMaquina, avaliacao):
        estado.limpar_alerta()
        self._votar(estado, avaliacao)
        historico = list(estado.historico)
        base = await asyncio.to_thread(self._linha_de_base, historico)
        dados = self._dados_alerta(maquina_id, estado, avaliacao)
        alerta = await self.armazenamento.criar_alerta({**dados, "linha_de_base": base})
        if alerta:
            estado.alerta = alerta
            if base:
                estado.base_congelada = base
                # Os últimos 3 min ficam fora da base e podem já conter a falha
                estado.historico_limpo = historico[:-JANELA_TENDENCIA]
            await self.notificar("alerta_criado", alerta)
        else:
            estado.limpar_alerta()

    async def _atualizar(self, maquina_id: int, estado: EstadoMaquina, avaliacao):
        alerta = await self.armazenamento.atualizar_alerta(
            estado.alerta["id"], self._dados_alerta(maquina_id, estado, avaliacao)
        )
        if alerta:
            estado.alerta = alerta
            await self.notificar("alerta_atualizado", alerta)

    async def _encerrar(
        self, estado: EstadoMaquina, manter_recentes: int | None = None
    ):
        """Encerra o alerta e tira as leituras da falha do histórico.

        `manter_recentes` são as últimas leituras já normais que continuam nele.
        """
        alerta = await self.armazenamento.encerrar_alerta(estado.alerta["id"])
        if estado.base_congelada is not None:
            if manter_recentes is None:
                manter_recentes = self.leituras_encerramento
            recentes = (
                list(estado.historico)[-manter_recentes:] if manter_recentes else []
            )
            estado.historico.clear()
            estado.historico.extend((estado.historico_limpo or []) + recentes)
        estado.limpar_alerta()
        if alerta:
            await self.notificar("alerta_encerrado", alerta)

    # ---------- diagnóstico do próprio monitor ----------

    def status(self) -> dict:
        maquinas = []
        for maquina_id, estado in sorted(self.estados.items()):
            avaliacao = estado.ultima_avaliacao
            maquinas.append(
                {
                    "maquina_id": maquina_id,
                    "leituras_no_historico": len(estado.historico),
                    "aquecida": len(estado.historico) >= LEITURAS_AQUECIMENTO,
                    "anomalias_seguidas": estado.anomalias_seguidas,
                    "alerta_aberto_id": estado.alerta["id"] if estado.alerta else None,
                    "ultima_pontuacao": (
                        None if avaliacao is None else round(avaliacao.pontuacao, 4)
                    ),
                    "ultimo_diagnostico": (
                        None if avaliacao is None else avaliacao.diagnostico
                    ),
                }
            )
        resposta = {
            "habilitado": self.habilitado,
            "aviso": aviso_modelo,
            "maquinas": maquinas,
        }
        if self.habilitado:
            deteccao = self.modelo.metricas.get("deteccao", {})
            diagnostico = self.modelo.metricas.get("diagnostico", {})
            resposta["modelo"] = {
                "treinado_em": self.modelo.treinado_em,
                "versao_sklearn": self.modelo.versao_sklearn,
                "leituras_confirmacao": self.modelo.leituras_confirmacao,
                "leituras_encerramento": self.leituras_encerramento,
                "taxa_deteccao": deteccao.get("taxa_deteccao"),
                "alarmes_falsos_por_maquina_dia": deteccao.get(
                    "alarmes_falsos_por_maquina_dia"
                ),
                "acuracia_diagnostico": diagnostico.get("acuracia"),
            }
        return resposta


class ArmazenamentoPostgres:
    """Implementação real do Armazenamento, usando o pool da API."""

    def __init__(self, obter_pool: Callable):
        self.obter_pool = obter_pool

    async def _executar(self, funcao, *args):
        async with self.obter_pool().acquire() as conn:
            return await funcao(conn, *args)

    async def criar_alerta(self, dados):
        return await self._executar(repository.criar_alerta, dados)

    async def atualizar_alerta(self, alerta_id, dados):
        return await self._executar(repository.atualizar_alerta, alerta_id, dados)

    async def encerrar_alerta(self, alerta_id):
        return await self._executar(repository.encerrar_alerta, alerta_id)

    async def listar_alertas_abertos(self):
        return await self._executar(repository.listar_alertas, None, True, 1000)

    async def listar_maquinas(self):
        maquinas = await self._executar(repository.listar_maquinas_cadastradas)
        return [m["id"] for m in maquinas]

    async def leituras_recentes(self, maquina_id, limite):
        return await self._executar(
            repository.buscar_leituras_recentes, maquina_id, limite
        )
