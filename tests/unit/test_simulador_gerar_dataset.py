import asyncio
import csv

import pytest

from simulador import gerar_dataset
from simulador.rotulos import COLUNAS


def ler(caminho):
    with caminho.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


@pytest.mark.parametrize("seed", [1, 2])
def test_gera_sessoes_rotuladas_sem_api(tmp_path, seed):
    saida = tmp_path / "dataset.csv"

    falhas = asyncio.run(
        gerar_dataset.gerar(saida, sessoes=2, horas=1, intervalo_s=2, seed=seed)
    )
    linhas = ler(saida)

    maquinas = len(gerar_dataset.MAQUINAS_PADRAO)
    assert len(linhas) == 2 * 1800 * maquinas
    assert tuple(linhas[0]) == COLUNAS
    assert {linha["sessao"] for linha in linhas} == {
        f"offline-s{seed}-01",
        f"offline-s{seed}-02",
    }
    assert falhas > 0
    assert {linha["resultado_envio"] for linha in linhas} == {"gerado_offline"}
    assert "normal" in {linha["cenario"] for linha in linhas}
    # Linhas com falha registram intensidade; linhas normais não
    for linha in linhas:
        if linha["cenario"] == "normal":
            assert float(linha["intensidade"]) == 0
        else:
            assert float(linha["intensidade"]) > 0


def test_mesma_semente_gera_o_mesmo_dataset(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"

    asyncio.run(gerar_dataset.gerar(a, sessoes=1, horas=0.5, intervalo_s=2, seed=9))
    asyncio.run(gerar_dataset.gerar(b, sessoes=1, horas=0.5, intervalo_s=2, seed=9))

    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_gerar_de_novo_substitui_o_arquivo(tmp_path):
    saida = tmp_path / "dataset.csv"

    asyncio.run(gerar_dataset.gerar(saida, sessoes=1, horas=0.1, intervalo_s=2, seed=1))
    asyncio.run(gerar_dataset.gerar(saida, sessoes=1, horas=0.1, intervalo_s=2, seed=1))

    assert len(ler(saida)) == 180 * len(gerar_dataset.MAQUINAS_PADRAO)


def test_horario_simulado_avanca_com_o_intervalo(tmp_path):
    saida = tmp_path / "dataset.csv"

    asyncio.run(
        gerar_dataset.gerar(saida, sessoes=1, horas=0.01, intervalo_s=2, seed=1)
    )
    horarios = sorted({linha["registrado_em_utc"] for linha in ler(saida)})

    assert horarios[0] == "2026-01-05T06:00:00+00:00"
    assert horarios[1] == "2026-01-05T06:00:02+00:00"


def test_linha_de_comando(tmp_path, capsys):
    saida = tmp_path / "cli.csv"

    gerar_dataset.main(
        ["--sessoes", "1", "--horas", "0.2", "--seed", "3", "--saida", str(saida)]
    )

    assert saida.exists()
    assert "leituras" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cliente_offline_descarrega_sem_buffer():
    from simulador.gerar_dataset import ClienteOffline

    cliente = ClienteOffline([])
    assert await cliente.descarregar_buffer() == 0
