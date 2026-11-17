"""Painel do simulador de ESP32.

Execute a partir da raiz do repositório:
    python -m simulador.main
"""

import hmac
import time

from fastapi.responses import RedirectResponse
from nicegui import app, background_tasks, ui

from simulador import config
from simulador.cliente_api import ClienteAPI, ResultadoEnvio
from simulador.estado import EstadoMaquina, Simulador
from simulador.fisica import (
    CENARIOS,
    LIMITE_FREQUENCIA_HZ,
    LIMITE_TENSAO_V,
    STATUS_OPERACAO,
)
from simulador.rotulos import GravadorRotulos

cliente = ClienteAPI(config.API_BASE_URL, config.API_KEY)
simulador = Simulador(
    cliente,
    GravadorRotulos(config.ARQUIVO_ROTULOS),
    intervalo_envio_s=config.INTERVALO_ENVIO_S,
    intervalo_sincronizacao_s=config.INTERVALO_SINCRONIZACAO_S,
)


async def _iniciar() -> None:
    background_tasks.create(simulador.executar(), name="simulador")


async def _encerrar() -> None:
    await cliente.fechar()


app.on_startup(_iniciar)
app.on_shutdown(_encerrar)

# campo, rótulo, unidade, mínimo, máximo, passo, casas decimais
SLIDERS = (
    ("tensao_volt", "Tensão", "V", 0, LIMITE_TENSAO_V, 0.5, 1),
    ("corrente_ampere", "Corrente", "A", 0, 80, 0.1, 1),
    ("fator_potencia", "Fator de potência", "", 0.5, 1.0, 0.01, 2),
    ("vibracao_rms", "Vibração", "g", 0, 20, 0.05, 2),
    ("frequencia_hz", "Frequência", "Hz", 0, LIMITE_FREQUENCIA_HZ, 0.1, 1),
)

COR_STATUS = {
    "Ativa": "positive",
    "Inativa": "warning",
    "Desligada": "grey-7",
    "Manutenção": "info",
}

ICONE_RESULTADO = {
    ResultadoEnvio.ENVIADO: (
        "check_circle",
        "text-green-400",
        "Leitura entregue à API",
    ),
    ResultadoEnvio.BUFFER: (
        "cloud_off",
        "text-amber-400",
        "API fora do ar: leitura guardada no buffer",
    ),
    ResultadoEnvio.REJEITADO: ("error", "text-red-400", "A API recusou a leitura"),
}


def _autenticado() -> bool:
    return not config.PAINEL_SENHA or app.storage.user.get("autenticado", False)


def _aplicar_tema() -> None:
    ui.colors(primary="#8b5cf6", secondary="#22d3ee", accent="#a78bfa")
    ui.query("body").classes("bg-slate-950")


# ==========================================
# CARD DE UMA MÁQUINA
# ==========================================


def _card_maquina(m: EstadoMaquina):
    """Desenha o card e devolve a função que o atualiza a cada segundo."""

    async def enviar_agora() -> None:
        if m.enviando:
            await simulador.enviar_maquina(m)

    def iniciar_cenario(chave: str) -> None:
        m.iniciar_cenario(chave, time.monotonic())
        ui.notify(f"{m.tag}: cenário '{CENARIOS[chave].nome}' iniciado", type="warning")

    with ui.card().classes("w-full gap-3 bg-slate-900 border border-slate-800"):
        # Cabeçalho
        with ui.row().classes("w-full items-center no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label().classes("text-lg font-bold").bind_text_from(m, "tag")
                ui.label().classes("text-xs text-slate-400").bind_text_from(
                    m,
                    "nome",
                    backward=lambda nome: f"{nome} · {m.setor or 'sem setor'}",
                )
            ui.space()
            chip_status = ui.badge("—").classes("text-sm px-2 py-1")
            icone_resultado = ui.icon("hourglass_empty", size="sm").classes(
                "text-slate-500"
            )
            with icone_resultado:
                dica_resultado = ui.tooltip("Nenhuma leitura enviada ainda")

        ui.label(
            "🔧 Ordem de manutenção aberta na API: a máquina reporta 'Manutenção'"
        ).classes(
            "w-full text-xs text-sky-300 bg-sky-950 rounded px-2 py-1"
        ).bind_visibility_from(m, "em_manutencao")

        # Status e modos
        toggle_status = (
            ui.toggle(list(STATUS_OPERACAO))
            .props("dense no-caps")
            .bind_value(m, "status")
        )
        with ui.row().classes("gap-4"):
            ui.switch("Automático").props("dense").bind_value(
                m, "modo_automatico"
            ).tooltip("Alterna paradas sozinho, como no chão de fábrica")
            ui.switch("Ruído").props("dense").bind_value(m, "ruido").tooltip(
                "Variação aleatória realista sobre os valores base"
            )
            ui.switch("Enviando").props("dense color=positive").bind_value(
                m, "enviando"
            )

        ui.separator().classes("bg-slate-800")

        # Sliders
        for campo, rotulo, unidade, minimo, maximo, passo, casas in SLIDERS:
            with ui.column().classes("w-full gap-0"):
                with ui.row().classes("w-full justify-between text-sm"):
                    ui.label(rotulo).classes("text-slate-300")
                    ui.label().classes("font-mono").bind_text_from(
                        m.parametros,
                        campo,
                        backward=lambda v, c=casas, u=unidade: f"{v:.{c}f} {u}".strip(),
                    )
                ui.slider(min=minimo, max=maximo, step=passo).props("dense").bind_value(
                    m.parametros, campo
                ).on("change", enviar_agora)

        with ui.row().classes("w-full justify-between text-sm"):
            ui.label("Potência calculada (V × I × FP)").classes("text-slate-300")
            rotulo_potencia = ui.label().classes("font-mono text-violet-300")

        ui.separator().classes("bg-slate-800")

        # Cenários de falha
        ui.label("Cenários de falha").classes("text-sm text-slate-300")
        with ui.row().classes("gap-2"):
            for cenario in CENARIOS.values():
                ui.button(
                    cenario.nome,
                    icon=cenario.icone,
                    on_click=lambda c=cenario.chave: iniciar_cenario(c),
                ).props("outline dense no-caps size=sm color=warning").tooltip(
                    cenario.descricao
                )

        linha_cenario = ui.row().classes("w-full items-center no-wrap gap-2")
        with linha_cenario:
            rotulo_cenario = ui.label().classes(
                "text-xs text-amber-300 whitespace-nowrap"
            )
            barra_cenario = ui.linear_progress(
                show_value=False, color="warning"
            ).classes("grow")
            ui.button(icon="stop", on_click=m.encerrar_cenario).props(
                "flat dense round size=sm color=warning"
            ).tooltip("Encerrar cenário")

        # Gráfico das últimas leituras
        grafico = ui.echart(
            {
                "animation": False,
                "backgroundColor": "transparent",
                "grid": {"left": 36, "right": 36, "top": 28, "bottom": 8},
                "tooltip": {"trigger": "axis"},
                "legend": {"top": 0, "textStyle": {"color": "#cbd5e1", "fontSize": 11}},
                "xAxis": {"type": "category", "data": [], "axisLabel": {"show": False}},
                "yAxis": [
                    {
                        "type": "value",
                        "axisLabel": {"color": "#94a3b8", "fontSize": 10},
                        "splitLine": {"lineStyle": {"color": "#1e293b"}},
                    },
                    {
                        "type": "value",
                        "axisLabel": {"color": "#94a3b8", "fontSize": 10},
                        "splitLine": {"show": False},
                    },
                ],
                "series": [
                    {
                        "name": "Corrente (A)",
                        "type": "line",
                        "showSymbol": False,
                        "smooth": True,
                        "color": "#22d3ee",
                        "data": [],
                    },
                    {
                        "name": "Vibração (g)",
                        "type": "line",
                        "yAxisIndex": 1,
                        "showSymbol": False,
                        "smooth": True,
                        "color": "#a78bfa",
                        "data": [],
                    },
                ],
            }
        ).classes("w-full h-40")

        # Rodapé
        with ui.row().classes("w-full items-center no-wrap"):
            rotulo_leitura = ui.label("Aguardando primeira leitura…").classes(
                "text-xs font-mono text-slate-400"
            )
            ui.space()
            ui.button(icon="restart_alt", on_click=m.restaurar_perfil).props(
                "flat dense round size=sm"
            ).tooltip("Restaurar valores nominais")
            ui.button(icon="send", on_click=enviar_agora).props(
                "flat dense round size=sm"
            ).tooltip("Enviar leitura agora")

    ultimo_ponto = {"hora": None}

    def atualizar() -> None:
        agora = time.monotonic()
        m.atualizar_cenario(agora)

        rotulo_potencia.text = f"{m.parametros.potencia_watt:,.0f} W".replace(",", ".")
        toggle_status.set_enabled(not m.modo_automatico and not m.em_manutencao)

        leitura = m.ultima_leitura
        if leitura:
            status = leitura["status_atual"]
            chip_status.text = status
            chip_status.props(f"color={COR_STATUS.get(status, 'grey')}")
            rotulo_leitura.text = (
                f"{leitura['tensao_volt']:.1f} V · {leitura['corrente_ampere']:.2f} A · "
                f"{leitura['potencia_watt']:.0f} W · {leitura['vibracao_rms']:.2f} g · "
                f"{leitura['frequencia_hz']:.1f} Hz"
            )
        if m.ultimo_resultado:
            nome, cor, dica = ICONE_RESULTADO[m.ultimo_resultado]
            icone_resultado.name = nome
            icone_resultado.classes(replace=cor)
            dica_resultado.text = dica

        linha_cenario.set_visibility(m.cenario is not None)
        if m.cenario:
            cenario = CENARIOS[m.cenario]
            restante = cenario.duracao_s * (1 - m.progresso_cenario(agora))
            rotulo_cenario.text = f"⚠ {cenario.nome} · {restante:.0f}s"
            barra_cenario.value = m.progresso_cenario(agora)

        if m.historico and m.historico[-1]["hora"] != ultimo_ponto["hora"]:
            ultimo_ponto["hora"] = m.historico[-1]["hora"]
            pontos = list(m.historico)
            grafico.options["xAxis"]["data"] = [p["hora"] for p in pontos]
            grafico.options["series"][0]["data"] = [
                p["corrente_ampere"] for p in pontos
            ]
            grafico.options["series"][1]["data"] = [p["vibracao_rms"] for p in pontos]
            grafico.update()

    atualizar()
    return atualizar


# ==========================================
# PÁGINAS
# ==========================================


@ui.page("/")
def painel():
    if not _autenticado():
        return RedirectResponse("/login")

    _aplicar_tema()
    atualizadores: list = []
    renderizado = {"ids": None}

    async def sincronizar() -> None:
        if await simulador.sincronizar_maquinas():
            ui.notify("Máquinas sincronizadas com a API", type="positive")
        else:
            ui.notify(cliente.ultimo_erro or "Falha ao sincronizar", type="negative")

    def definir_envio(ligado: bool) -> None:
        for m in simulador.maquinas.values():
            m.enviando = ligado

    def baixar_rotulos() -> None:
        if config.ARQUIVO_ROTULOS.exists():
            ui.download.file(config.ARQUIVO_ROTULOS, "rotulos.csv")
        else:
            ui.notify("Ainda não há leituras gravadas", type="info")

    with ui.header().classes(
        "bg-slate-900 border-b border-slate-800 items-center gap-3 px-4"
    ):
        ui.icon("memory", size="md").classes("text-violet-400")
        with ui.column().classes("gap-0"):
            ui.label("Simulador ESP32").classes("text-lg font-bold leading-tight")
            ui.label(f"Simple IHM · enviando para {config.API_BASE_URL}").classes(
                "text-xs text-slate-400"
            )
        ui.space()
        chip_api = ui.badge("API: aguardando").classes("px-2 py-1")
        rotulo_buffer = ui.label().classes("text-xs text-amber-300")
        with ui.button(icon="more_vert").props("flat round color=white"):
            with ui.menu():
                ui.menu_item("Sincronizar máquinas", on_click=sincronizar)
                ui.menu_item("Pausar todas", on_click=lambda: definir_envio(False))
                ui.menu_item("Retomar todas", on_click=lambda: definir_envio(True))
                ui.separator()
                ui.menu_item("Baixar rótulos (CSV)", on_click=baixar_rotulos)

    rotulo_erro = ui.label().classes(
        "w-full text-sm text-red-300 bg-red-950 border border-red-900 rounded px-3 py-2"
    )

    @ui.refreshable
    def grade() -> None:
        atualizadores.clear()
        renderizado["ids"] = tuple(simulador.maquinas)
        if not simulador.maquinas:
            with ui.column().classes("w-full items-center py-16 text-slate-400"):
                ui.spinner(size="lg")
                ui.label("Aguardando a lista de máquinas da API…")
            return
        with ui.element("div").classes(
            "w-full grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4"
        ):
            for maquina in simulador.maquinas.values():
                atualizadores.append(_card_maquina(maquina))

    grade()

    def atualizar_pagina() -> None:
        if tuple(simulador.maquinas) != renderizado["ids"]:
            grade.refresh()

        if cliente.online is None:
            chip_api.text, cor = "API: aguardando", "grey"
        elif cliente.online and not cliente.ultimo_erro:
            chip_api.text, cor = "API: online", "positive"
        elif cliente.online:
            chip_api.text, cor = "API: recusando", "negative"
        else:
            chip_api.text, cor = "API: offline", "negative"
        chip_api.props(f"color={cor}")

        rotulo_buffer.text = (
            f"{len(cliente.buffer)} no buffer" if cliente.buffer else ""
        )
        rotulo_erro.text = f"⚠ {cliente.ultimo_erro}" if cliente.ultimo_erro else ""
        rotulo_erro.set_visibility(bool(cliente.ultimo_erro))

        for atualizar in atualizadores:
            atualizar()

    atualizar_pagina()
    ui.timer(1.0, atualizar_pagina)


@ui.page("/login")
def login():
    if _autenticado():
        return RedirectResponse("/")

    _aplicar_tema()

    def entrar() -> None:
        if hmac.compare_digest(senha.value.encode(), config.PAINEL_SENHA.encode()):
            app.storage.user["autenticado"] = True
            ui.navigate.to("/")
        else:
            ui.notify("Senha incorreta", type="negative")

    with ui.card().classes(
        "absolute-center w-80 gap-4 bg-slate-900 border border-slate-800"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.icon("memory", size="md").classes("text-violet-400")
            ui.label("Simulador ESP32").classes("text-lg font-bold")
        senha = (
            ui.input("Senha do painel", password=True, password_toggle_button=True)
            .classes("w-full")
            .on("keydown.enter", entrar)
        )
        ui.button("Entrar", on_click=entrar).classes("w-full")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host="0.0.0.0",
        port=config.PORTA,
        title="Simulador ESP32 · Simple IHM",
        favicon="⚙️",
        dark=True,
        language="pt-BR",
        reload=False,
        show=False,
        storage_secret=config.STORAGE_SECRET,
    )
