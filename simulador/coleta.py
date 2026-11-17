"""Coleta automática de dados: dispara falhas variadas em intervalos aleatórios.

Se toda falha fosse idêntica, o modelo só decoraria a fórmula do simulador.
Por isso cada disparo sorteia o tipo, a intensidade e a duração.
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from simulador.fisica import CENARIOS


@dataclass(frozen=True)
class ConfigColeta:
    # Tempo de operação normal entre uma falha e a próxima, por máquina
    pausa_min_s: float = 120
    pausa_max_s: float = 480
    # Força da falha (1.0 = efeito padrão dos botões do painel)
    intensidade_min: float = 0.5
    intensidade_max: float = 1.5
    # Duração em relação à padrão (0.6 = 40% mais rápida)
    fator_duracao_min: float = 0.6
    fator_duracao_max: float = 1.6


class ColetaAutomatica:
    def __init__(self, rng: random.Random, config: ConfigColeta = ConfigColeta()):
        self.rng = rng
        self.config = config
        self.ativa = False
        self.sessao: str | None = None
        self.inicio: float | None = None
        self.falhas_disparadas = 0
        self._proxima_falha: dict[int, float] = {}

    def iniciar(self, agora: float, sessao: str | None = None) -> None:
        self.ativa = True
        self.sessao = sessao or datetime.now().strftime("coleta-%Y%m%d-%H%M%S")
        self.inicio = agora
        self.falhas_disparadas = 0
        self._proxima_falha.clear()

    def parar(self) -> None:
        self.ativa = False
        self._proxima_falha.clear()

    def _sortear_pausa(self) -> float:
        return self.rng.uniform(self.config.pausa_min_s, self.config.pausa_max_s)

    def passo(self, maquinas: Iterable, agora: float) -> list[tuple[int, str]]:
        """Dispara as falhas que chegaram na hora. Retorna (maquina_id, cenário)."""
        if not self.ativa:
            return []

        disparos = []
        for m in maquinas:
            m.atualizar_cenario(agora)
            pode_falhar = m.enviando and not m.em_manutencao and m.status == "Ativa"
            if not pode_falhar or m.cenario_ativo:
                # A pausa só começa a contar quando a máquina volta ao normal
                self._proxima_falha.pop(m.id, None)
                continue

            if m.id not in self._proxima_falha:
                self._proxima_falha[m.id] = agora + self._sortear_pausa()
                continue

            if agora >= self._proxima_falha[m.id]:
                del self._proxima_falha[m.id]
                chave = self.rng.choice(list(CENARIOS))
                c = self.config
                m.iniciar_cenario(
                    chave,
                    agora,
                    duracao_s=CENARIOS[chave].duracao_s
                    * self.rng.uniform(c.fator_duracao_min, c.fator_duracao_max),
                    intensidade=self.rng.uniform(c.intensidade_min, c.intensidade_max),
                )
                self.falhas_disparadas += 1
                disparos.append((m.id, chave))
        return disparos
