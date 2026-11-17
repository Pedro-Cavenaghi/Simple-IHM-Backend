"""Estado das máquinas virtuais e o laço que envia as leituras para a API."""

import asyncio
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from simulador.cliente_api import ClienteAPI, ResultadoEnvio
from simulador.fisica import (
    CENARIOS,
    STATUS_MANUTENCAO,
    Parametros,
    gerar_leitura,
    perfil_padrao,
)
from simulador.rotulos import GravadorRotulos

TAMANHO_HISTORICO = 60

# Modo automático: probabilidade de cada próximo estado e quanto tempo ele dura (s)
PESOS_AUTOMATICO = {"Ativa": 90, "Inativa": 8, "Desligada": 2}
DURACAO_AUTOMATICO = {"Ativa": (60, 240), "Inativa": (10, 40), "Desligada": (20, 60)}


@dataclass
class EstadoMaquina:
    id: int
    tag: str
    nome: str
    setor: str | None
    parametros: Parametros
    status: str = "Ativa"  # escolhido no painel
    modo_automatico: bool = False  # alterna paradas sozinho, como no chão de fábrica
    ruido: bool = True
    enviando: bool = True
    em_manutencao: bool = False  # vem da API (ordem aberta para hoje)
    cenario: str | None = None
    cenario_inicio: float = 0.0
    ultima_leitura: dict | None = None
    ultimo_resultado: ResultadoEnvio | None = None
    historico: deque = field(default_factory=lambda: deque(maxlen=TAMANHO_HISTORICO))
    _status_auto: str = "Ativa"
    _status_auto_ate: float = 0.0

    @classmethod
    def a_partir_da_api(cls, dados: dict) -> "EstadoMaquina":
        return cls(
            id=dados["id"],
            tag=dados["tag_maquina"],
            nome=dados["nome_maquina"],
            setor=dados.get("setor"),
            parametros=perfil_padrao(dados["tag_maquina"]),
            em_manutencao=bool(dados.get("em_manutencao", False)),
        )

    # ---------- cenários ----------

    def iniciar_cenario(self, chave: str, agora: float) -> None:
        if chave not in CENARIOS:
            raise ValueError(f"Cenário desconhecido: {chave}")
        self.cenario = chave
        self.cenario_inicio = agora

    def encerrar_cenario(self) -> None:
        self.cenario = None

    def atualizar_cenario(self, agora: float) -> None:
        """Encerra o cenário quando a duração termina."""
        if (
            self.cenario
            and agora - self.cenario_inicio >= CENARIOS[self.cenario].duracao_s
        ):
            self.cenario = None

    def progresso_cenario(self, agora: float) -> float:
        if not self.cenario:
            return 0.0
        duracao = CENARIOS[self.cenario].duracao_s
        return min(1.0, max(0.0, (agora - self.cenario_inicio) / duracao))

    # ---------- valores efetivos ----------

    def parametros_efetivos(self, agora: float) -> Parametros:
        self.atualizar_cenario(agora)
        if not self.cenario:
            return self.parametros
        return CENARIOS[self.cenario].aplicar(
            self.parametros, agora - self.cenario_inicio
        )

    def status_efetivo(self, agora: float, rng: random.Random) -> str:
        if self.em_manutencao:
            return STATUS_MANUTENCAO
        if not self.modo_automatico:
            return self.status
        if agora >= self._status_auto_ate:
            estados = list(PESOS_AUTOMATICO)
            self._status_auto = rng.choices(estados, weights=PESOS_AUTOMATICO.values())[
                0
            ]
            minimo, maximo = DURACAO_AUTOMATICO[self._status_auto]
            self._status_auto_ate = agora + rng.uniform(minimo, maximo)
        return self._status_auto

    @property
    def parametros_alterados(self) -> bool:
        """Se os sliders saíram do perfil nominal (útil para separar dados 'limpos')."""
        return self.parametros != perfil_padrao(self.tag)

    def restaurar_perfil(self) -> None:
        padrao = perfil_padrao(self.tag)
        # Atualiza o objeto existente, porque os sliders estão ligados a ele
        for campo, valor in vars(padrao).items():
            setattr(self.parametros, campo, valor)

    def rotulo(self) -> str:
        if self.em_manutencao:
            return "manutencao"
        return self.cenario or "normal"


class Simulador:
    def __init__(
        self,
        cliente: ClienteAPI,
        gravador: GravadorRotulos | None,
        intervalo_envio_s: float,
        intervalo_sincronizacao_s: float,
        rng: random.Random | None = None,
        relogio: Callable[[], float] = time.monotonic,
        enviar_por_padrao: bool = True,
    ):
        self.cliente = cliente
        self.gravador = gravador
        self.intervalo_envio_s = intervalo_envio_s
        self.intervalo_sincronizacao_s = intervalo_sincronizacao_s
        self.rng = rng or random.Random()
        self.relogio = relogio
        self.maquinas: dict[int, EstadoMaquina] = {}
        self.ultima_sincronizacao: float | None = None
        # Vale para as máquinas que ainda vão aparecer na sincronização
        self.enviar_por_padrao = enviar_por_padrao

    async def sincronizar_maquinas(self) -> bool:
        """Atualiza a lista de máquinas e o estado de manutenção a partir da API."""
        dados = await self.cliente.listar_maquinas()
        if dados is None:
            return False

        ids_api = set()
        for item in dados:
            ids_api.add(item["id"])
            existente = self.maquinas.get(item["id"])
            if existente is None:
                nova = EstadoMaquina.a_partir_da_api(item)
                nova.enviando = self.enviar_por_padrao
                self.maquinas[item["id"]] = nova
            else:
                existente.tag = item["tag_maquina"]
                existente.nome = item["nome_maquina"]
                existente.setor = item.get("setor")
                existente.em_manutencao = bool(item.get("em_manutencao", False))

        for maquina_id in set(self.maquinas) - ids_api:
            del self.maquinas[maquina_id]

        self.ultima_sincronizacao = self.relogio()
        return True

    async def enviar_maquina(self, maquina: EstadoMaquina) -> ResultadoEnvio:
        agora = self.relogio()
        leitura = gerar_leitura(
            maquina.id,
            maquina.parametros_efetivos(agora),
            maquina.status_efetivo(agora, self.rng),
            ruido=maquina.ruido,
            rng=self.rng,
        )
        resultado = await self.cliente.enviar(leitura)

        maquina.ultima_leitura = leitura
        maquina.ultimo_resultado = resultado
        maquina.historico.append(
            {"hora": datetime.now().strftime("%H:%M:%S"), **leitura}
        )

        if self.gravador:
            self.gravador.registrar(
                leitura,
                tag_maquina=maquina.tag,
                cenario=maquina.rotulo(),
                parametros_alterados=maquina.parametros_alterados,
                resultado_envio=resultado.value,
            )
        return resultado

    @property
    def todas_pausadas(self) -> bool:
        return not any(m.enviando for m in self.maquinas.values())

    def pausar_todas(self) -> None:
        self.enviar_por_padrao = False
        for m in self.maquinas.values():
            m.enviando = False

    def retomar_todas(self) -> None:
        self.enviar_por_padrao = True
        for m in self.maquinas.values():
            m.enviando = True

    async def desligar_todas(self) -> list[ResultadoEnvio]:
        """Envia uma última leitura 'Desligada' de cada máquina e pausa o envio.

        Sem isso, o dashboard continuaria mostrando a última leitura como atual.
        Máquinas com manutenção aberta continuam reportando 'Manutenção'.
        """
        self.pausar_todas()
        for m in self.maquinas.values():
            m.status = "Desligada"
            m.modo_automatico = False
            m.encerrar_cenario()
        return await asyncio.gather(
            *(self.enviar_maquina(m) for m in self.maquinas.values())
        )

    async def ciclo(self) -> None:
        ativas = [m for m in self.maquinas.values() if m.enviando]
        if ativas:
            await asyncio.gather(*(self.enviar_maquina(m) for m in ativas))
        elif self.cliente.buffer:
            # Mesmo pausado, entrega o que ficou guardado durante uma queda da API
            await self.cliente.descarregar_buffer()

    async def executar(self) -> None:
        """Laço principal: sincroniza periodicamente e envia uma leitura por ciclo."""
        while True:
            agora = self.relogio()
            if (
                self.ultima_sincronizacao is None
                or agora - self.ultima_sincronizacao >= self.intervalo_sincronizacao_s
            ):
                if not await self.sincronizar_maquinas():
                    # Sem API: tenta de novo no próximo ciclo em vez de esperar 15 s
                    self.ultima_sincronizacao = None
            await self.ciclo()
            await asyncio.sleep(self.intervalo_envio_s)
