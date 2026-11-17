import csv

from simulador.rotulos import COLUNAS, GravadorRotulos

LEITURA = {
    "maquina_id": 1,
    "status_atual": "Ativa",
    "tensao_volt": 220.0,
    "corrente_ampere": 15.0,
    "potencia_watt": 2805.0,
    "vibracao_rms": 1.5,
    "frequencia_hz": 60.0,
}


def registrar(gravador, **extra):
    gravador.registrar(
        LEITURA,
        tag_maquina="CNC-01",
        cenario="normal",
        parametros_alterados=False,
        resultado_envio="enviado",
        **extra,
    )


def ler(arquivo):
    with arquivo.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_cria_arquivo_com_cabecalho(tmp_path):
    arquivo = tmp_path / "sub" / "rotulos.csv"
    gravador = GravadorRotulos(arquivo)

    registrar(gravador)
    registrar(gravador, sessao="s1")
    gravador.fechar()

    linhas = ler(arquivo)
    assert tuple(linhas[0]) == COLUNAS
    assert [linha["sessao"] for linha in linhas] == ["manual", "s1"]


def test_continua_arquivo_existente_do_mesmo_formato(tmp_path):
    arquivo = tmp_path / "rotulos.csv"
    primeiro = GravadorRotulos(arquivo)
    registrar(primeiro)
    primeiro.fechar()

    segundo = GravadorRotulos(arquivo)
    registrar(segundo)
    segundo.fechar()

    assert len(ler(arquivo)) == 2


def test_arquiva_csv_de_formato_antigo(tmp_path):
    arquivo = tmp_path / "rotulos.csv"
    arquivo.write_text(
        "registrado_em_utc,maquina_id,cenario\nx,1,normal\n", encoding="utf-8"
    )
    gravador = GravadorRotulos(arquivo)

    registrar(gravador)
    gravador.fechar()

    antigos = list(tmp_path.glob("rotulos-antigo-*.csv"))
    assert len(antigos) == 1
    assert "x,1,normal" in antigos[0].read_text(encoding="utf-8")
    assert len(ler(arquivo)) == 1


def test_linha_fica_no_disco_antes_de_fechar(tmp_path):
    """O CSV baixado pelo painel precisa estar completo com o arquivo ainda aberto."""
    arquivo = tmp_path / "rotulos.csv"
    gravador = GravadorRotulos(arquivo)

    registrar(gravador)

    assert len(arquivo.read_text(encoding="utf-8").splitlines()) == 2
    gravador.fechar()


def test_fechar_sem_ter_gravado_nao_falha(tmp_path):
    GravadorRotulos(tmp_path / "nada.csv").fechar()
