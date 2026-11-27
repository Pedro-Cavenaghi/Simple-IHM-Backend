"""Gera um dataset rotulado sem API, com relógio simulado.

Usa exatamente o mesmo motor do painel (física, cenários e coleta automática),
mas avança o tempo artificialmente: horas de operação saem em segundos, sem
gravar nada no banco. Cada sessão tem semente própria, para que treino e teste
possam ser separados por sessão.

Exemplo (a partir da raiz do repositório):
    python -m simulador.gerar_dataset --sessoes 6 --horas 12 --seed 42
"""

import argparse
import asyncio
import random
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from simulador.cliente_api import ResultadoEnvio
from simulador.coleta import ConfigColeta
from simulador.estado import Simulador
from simulador.rotulos import GravadorRotulos

# Uma máquina de cada perfil (EST usa o perfil genérico)
MAQUINAS_PADRAO = [
    {"id": 1, "tag_maquina": "CNC-01", "nome_maquina": "Torno CNC", "setor": None},
    {"id": 2, "tag_maquina": "INJ-01", "nome_maquina": "Injetora", "setor": None},
    {"id": 3, "tag_maquina": "PRE-01", "nome_maquina": "Prensa", "setor": None},
    {"id": 4, "tag_maquina": "EST-01", "nome_maquina": "Esteira", "setor": None},
]

INICIO_PADRAO = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)

# Falhas mais raras que na coleta ao vivo do painel (2 a 8 min, boa para demonstração):
# numa fábrica real a máquina passa a maior parte do tempo normal, e falhas frequentes
# demais contaminariam a linha de base de 30 min usada nas features.
PAUSA_MIN_PADRAO_MIN = 10
PAUSA_MAX_PADRAO_MIN = 30


class ClienteOffline:
    """Substitui a API: entrega a lista de máquinas e não envia nada."""

    def __init__(self, maquinas: list[dict]):
        self.maquinas = maquinas
        self.buffer: list = []

    async def listar_maquinas(self) -> list[dict]:
        return [{**m, "em_manutencao": False} for m in self.maquinas]

    async def enviar(self, leitura: dict) -> ResultadoEnvio:
        return ResultadoEnvio.GERADO_OFFLINE

    async def descarregar_buffer(self) -> int:
        return 0


class RelogioSimulado:
    def __init__(self, inicio_parede: datetime):
        self.segundos = 0.0
        self.inicio_parede = inicio_parede

    def monotonic(self) -> float:
        return self.segundos

    def parede(self) -> datetime:
        return self.inicio_parede + timedelta(seconds=self.segundos)


async def gerar_sessao(
    gravador: GravadorRotulos,
    sessao: str,
    horas: float,
    intervalo_s: float,
    seed: int,
    inicio: datetime,
    maquinas: list[dict] = MAQUINAS_PADRAO,
    config_coleta: ConfigColeta = ConfigColeta(),
) -> int:
    relogio = RelogioSimulado(inicio)
    simulador = Simulador(
        ClienteOffline(maquinas),
        gravador,
        intervalo_envio_s=intervalo_s,
        intervalo_sincronizacao_s=float("inf"),
        rng=random.Random(seed),
        relogio=relogio.monotonic,
        relogio_parede=relogio.parede,
        config_coleta=config_coleta,
    )
    await simulador.sincronizar_maquinas()
    simulador.iniciar_coleta(sessao)

    passos = int(horas * 3600 / intervalo_s)
    for _ in range(passos):
        await simulador.ciclo()
        relogio.segundos += intervalo_s
    return simulador.coleta.falhas_disparadas


async def gerar(
    saida: Path,
    sessoes: int,
    horas: float,
    intervalo_s: float,
    seed: int,
    pausa_min_s: float = PAUSA_MIN_PADRAO_MIN * 60,
    pausa_max_s: float = PAUSA_MAX_PADRAO_MIN * 60,
) -> int:
    if saida.exists():
        saida.unlink()  # cada geração é um dataset novo e reprodutível
    gravador = GravadorRotulos(saida)
    config = ConfigColeta(pausa_min_s=pausa_min_s, pausa_max_s=pausa_max_s)
    falhas = 0
    try:
        for i in range(sessoes):
            falhas += await gerar_sessao(
                gravador,
                sessao=f"offline-s{seed}-{i + 1:02d}",
                horas=horas,
                intervalo_s=intervalo_s,
                seed=seed * 1000 + i,
                # Sessões em dias diferentes, como coletas reais separadas
                inicio=INICIO_PADRAO + timedelta(days=i),
                config_coleta=config,
            )
    finally:
        gravador.fechar()
    return falhas


def _resumo(saida: Path) -> Counter:
    import csv

    with saida.open(encoding="utf-8") as arquivo:
        return Counter(linha["cenario"] for linha in csv.DictReader(arquivo))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessoes", type=int, default=6, help="sessões de coleta")
    parser.add_argument("--horas", type=float, default=12, help="horas por sessão")
    parser.add_argument(
        "--intervalo", type=float, default=2, help="segundos entre leituras"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="semente (reprodutibilidade)"
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("ml/dados/dataset.csv"),
        help="arquivo CSV de saída",
    )
    parser.add_argument(
        "--pausa-min",
        type=float,
        default=PAUSA_MIN_PADRAO_MIN,
        help="minutos mínimos de operação normal entre falhas",
    )
    parser.add_argument(
        "--pausa-max",
        type=float,
        default=PAUSA_MAX_PADRAO_MIN,
        help="minutos máximos de operação normal entre falhas",
    )
    args = parser.parse_args(argv)

    inicio = time.perf_counter()
    falhas = asyncio.run(
        gerar(
            args.saida,
            args.sessoes,
            args.horas,
            args.intervalo,
            args.seed,
            pausa_min_s=args.pausa_min * 60,
            pausa_max_s=args.pausa_max * 60,
        )
    )
    contagem = _resumo(args.saida)
    total = sum(contagem.values())

    print(f"Dataset gerado em {time.perf_counter() - inicio:.1f}s: {args.saida}")
    print(
        f"{args.sessoes} sessões × {args.horas:g} h · {total} leituras · "
        f"{falhas} falhas disparadas"
    )
    for cenario, quantidade in contagem.most_common():
        print(f"  {cenario:<20} {quantidade:>8}  ({quantidade / total:.1%})")


if __name__ == "__main__":
    main()  # pragma: no cover
