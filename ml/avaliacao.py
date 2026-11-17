"""Preparação dos dados rotulados e métricas por ocorrência de falha.

Métricas por linha enganam aqui: uma sobrecarga de 30 s tem 15 linhas e um
desgaste de 5 min tem 150. O que importa para a manutenção é: cada falha foi
detectada? Com quanta antecedência? Quantos alarmes falsos por dia?
"""

import numpy as np
import pandas as pd

from ml.features import (
    COLUNAS_FEATURES,
    JANELA_TENDENCIA,
    LEITURAS_POR_MINUTO,
    calcular_features,
    vibracao_relativa,
)
from ml.tendencia import GRAU_PADRAO, JANELA_PADRAO, minutos_ate_limite

SEGUNDOS_POR_LEITURA = 60 / LEITURAS_POR_MINUTO
NORMAL = "normal"


def preparar_dados(leituras: pd.DataFrame) -> pd.DataFrame:
    """Calcula features e marca ocorrências de falha e períodos de transição.

    Colunas adicionadas:
    - features (COLUNAS_FEATURES) e vibracao_relativa;
    - posicao: índice da leitura dentro da máquina/sessão;
    - evento: id da ocorrência de falha (-1 se normal);
    - posicao_no_evento: leituras desde o início da falha;
    - transicao: leitura normal nos 3 min seguintes a uma falha, quando as
      janelas ainda contêm a falha. Fica fora do treino e dos alarmes falsos;
    - valido: há histórico suficiente para todas as features.
    """
    ativas = leituras[leituras["status"] == "Ativa"].sort_values(
        ["sessao", "maquina_id", "registrado_em_utc"]
    )
    partes = []
    for _, grupo in ativas.groupby(["sessao", "maquina_id"], sort=False):
        grupo = grupo.reset_index(drop=True)
        features = calcular_features(grupo)
        grupo = pd.concat([grupo, features], axis=1)
        grupo["vibracao_relativa"] = vibracao_relativa(grupo)
        grupo["posicao"] = np.arange(len(grupo))

        falha = grupo["cenario"] != NORMAL
        inicio_evento = falha & (
            ~falha.shift(fill_value=False)
            | (grupo["cenario"] != grupo["cenario"].shift())
        )
        numero_evento = inicio_evento.cumsum()
        grupo["evento_local"] = numero_evento.where(falha, 0)
        grupo["posicao_no_evento"] = (
            grupo.groupby(numero_evento).cumcount().where(falha, -1)
        )

        ultima_falha = grupo["posicao"].where(falha).ffill()
        grupo["transicao"] = ~falha & (
            grupo["posicao"] - ultima_falha <= JANELA_TENDENCIA
        )
        partes.append(grupo)

    dados = pd.concat(partes, ignore_index=True)
    chave = dados["sessao"] + "#" + dados["maquina_id"].astype(str) + "#"
    dados["evento"] = np.where(
        dados["evento_local"] > 0,
        pd.factorize(chave + dados["evento_local"].astype(str))[0],
        -1,
    )
    dados = dados.drop(columns="evento_local")
    dados["valido"] = dados[list(COLUNAS_FEATURES)].notna().all(axis=1)
    return dados


def normal_limpo(dados: pd.DataFrame) -> pd.Series:
    return (dados["cenario"] == NORMAL) & ~dados["transicao"]


def _por_grupo(dados: pd.DataFrame, serie: np.ndarray, funcao) -> np.ndarray:
    resultado = np.empty(len(dados), dtype=serie.dtype)
    for indices in dados.groupby(["sessao", "maquina_id"], sort=False).indices.values():
        resultado[indices] = funcao(serie[indices])
    return resultado


def inicios_de_alerta(dados: pd.DataFrame, alertas: np.ndarray) -> np.ndarray:
    """True na primeira leitura de cada alerta (borda de subida)."""
    return _por_grupo(
        dados,
        np.asarray(alertas, dtype=bool),
        lambda a: a & ~np.concatenate([[False], a[:-1]]),
    )


def avaliar_deteccao(
    dados: pd.DataFrame, alertas: np.ndarray
) -> tuple[dict, pd.DataFrame]:
    """Detecção por ocorrência de falha e alarmes falsos por máquina-dia.

    `alertas` deve estar alinhado com `dados` (já confirmado por persistência).
    Uma falha conta como detectada se houver alerta durante ela ou na transição
    logo depois (as janelas levam alguns segundos para refletir a falha).
    """
    alertas = np.asarray(alertas, dtype=bool)
    posicao = dados["posicao"].to_numpy()
    grupo = (dados["sessao"] + "#" + dados["maquina_id"].astype(str)).to_numpy()

    linhas = []
    for evento, linhas_evento in dados[dados["evento"] >= 0].groupby("evento"):
        inicio, fim = linhas_evento.index.min(), linhas_evento.index.max()
        limite = min(fim + JANELA_TENDENCIA, len(dados) - 1)
        janela = np.arange(inicio, limite + 1)
        janela = janela[grupo[janela] == grupo[inicio]]
        com_alerta = janela[alertas[janela]]

        detectado = len(com_alerta) > 0
        atraso = (
            (posicao[com_alerta[0]] - posicao[inicio]) * SEGUNDOS_POR_LEITURA
            if detectado
            else np.nan
        )
        progresso = (
            dados.at[com_alerta[0], "cenario_progresso"]
            if detectado and com_alerta[0] <= fim
            else (1.0 if detectado else np.nan)
        )
        linhas.append(
            {
                "evento": evento,
                "cenario": linhas_evento["cenario"].iat[0],
                "intensidade": linhas_evento["intensidade"].iat[0],
                "duracao_s": len(linhas_evento) * SEGUNDOS_POR_LEITURA,
                "detectado": detectado,
                "atraso_s": atraso,
                "progresso_na_deteccao": progresso,
            }
        )
    eventos = pd.DataFrame(linhas)

    limpo = normal_limpo(dados).to_numpy() & dados["valido"].to_numpy()
    alarmes_falsos = int((inicios_de_alerta(dados, alertas) & limpo).sum())
    maquina_dias = limpo.sum() * SEGUNDOS_POR_LEITURA / 86400

    resumo = {
        "falhas": len(eventos),
        "taxa_deteccao": float(eventos["detectado"].mean()),
        "atraso_mediano_s": float(eventos["atraso_s"].median()),
        "alarmes_falsos": alarmes_falsos,
        "alarmes_falsos_por_maquina_dia": alarmes_falsos / maquina_dias,
        "por_cenario": {
            cenario: {
                "falhas": len(g),
                "taxa_deteccao": float(g["detectado"].mean()),
                "atraso_mediano_s": float(g["atraso_s"].median()),
                "progresso_mediano_na_deteccao": float(
                    g["progresso_na_deteccao"].median()
                ),
            }
            for cenario, g in eventos.groupby("cenario")
        },
    }
    return resumo, eventos


def avaliar_diagnostico(
    dados: pd.DataFrame, alertas: np.ndarray, classes: np.ndarray
) -> tuple[dict, pd.DataFrame]:
    """Acerto do diagnóstico por falha detectada (voto da maioria durante o alerta)."""
    alertas = np.asarray(alertas, dtype=bool)
    linhas = []
    for evento, linhas_evento in dados[dados["evento"] >= 0].groupby("evento"):
        indices = linhas_evento.index.to_numpy()
        votos = classes[indices[alertas[indices]]]
        if len(votos) == 0:
            continue
        valores, contagem = np.unique(votos, return_counts=True)
        linhas.append(
            {
                "evento": evento,
                "real": linhas_evento["cenario"].iat[0],
                "previsto": valores[contagem.argmax()],
            }
        )
    resultado = pd.DataFrame(linhas)
    acerto = resultado["real"] == resultado["previsto"]
    resumo = {
        "falhas_diagnosticadas": len(resultado),
        "acuracia": float(acerto.mean()),
        "acuracia_por_cenario": acerto.groupby(resultado["real"]).mean().to_dict(),
    }
    return resumo, resultado


def avaliar_prognostico(
    dados: pd.DataFrame,
    limite: float,
    marcos: tuple[float, ...] = (0.25, 0.5),
    janela: int = JANELA_PADRAO,
    grau: int = GRAU_PADRAO,
) -> tuple[dict, pd.DataFrame]:
    """Erro da regressão ao prever quando o desgaste cruza o limite de vibração.

    Para cada desgaste que realmente cruzou o limite, faz uma previsão no
    momento em que a vibração passou de cada `marco` (ex.: +25% e +50%) e
    compara com o momento real do cruzamento.
    """
    vibracao = dados["vibracao_relativa"].to_numpy()
    desvio = dados["vibracao_rms_desvio"].to_numpy()
    posicao = dados["posicao"].to_numpy()

    linhas = []
    desgastes = dados[
        (dados["evento"] >= 0) & (dados["cenario"] == "desgaste_rolamento")
    ]
    for evento, linhas_evento in desgastes.groupby("evento"):
        indices = linhas_evento.index.to_numpy()
        cruzou = indices[desvio[indices] >= limite]
        if len(cruzou) == 0:
            continue
        cruzamento = cruzou[0]
        for marco in marcos:
            passou = indices[(desvio[indices] >= marco) & (indices < cruzamento)]
            if len(passou) == 0:
                continue
            agora = passou[0]
            if posicao[agora] < janela - 1:
                continue  # histórico da máquina menor que a janela da regressão
            serie = vibracao[agora - janela + 1 : agora + 1]
            previsto = minutos_ate_limite(serie, limite, grau)
            real = (posicao[cruzamento] - posicao[agora]) * SEGUNDOS_POR_LEITURA / 60
            linhas.append(
                {
                    "evento": evento,
                    "marco": marco,
                    "real_min": real,
                    "previsto_min": previsto,
                }
            )
    previsoes = pd.DataFrame(linhas)
    com_previsao = previsoes.dropna(subset=["previsto_min"])
    erro = com_previsao["previsto_min"] - com_previsao["real_min"]
    resumo = {
        "previsoes": len(previsoes),
        "sem_tendencia_detectada": int(previsoes["previsto_min"].isna().sum()),
        "erro_absoluto_medio_min": float(erro.abs().mean()),
        # > 0: prevê o cruzamento mais tarde que o real; < 0: mais cedo (lado seguro)
        "erro_medio_min": float(erro.mean()),
        "por_marco": {
            str(marco): {
                "erro_absoluto_medio_min": float(
                    (g["previsto_min"] - g["real_min"]).abs().mean()
                ),
                "tempo_real_mediano_min": float(g["real_min"].median()),
            }
            for marco, g in com_previsao.groupby("marco")
        },
    }
    return resumo, previsoes
