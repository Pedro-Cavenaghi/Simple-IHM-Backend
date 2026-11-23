from datetime import date
from unittest.mock import AsyncMock

import pytest

import app.main as main_module
from tests.api.test_alertas import AGORA, alerta


def pendente(**extra):
    return alerta(
        manutencao_status="pendente",
        manutencao_descricao="Manutenção preditiva por provável sobrecarga.",
        manutencao_data_sugerida=date(2026, 11, 24),
        **extra,
    )


def aprovado():
    base = pendente(manutencao_id=7, analisado_por=4, analisado_em=AGORA)
    base["manutencao_status"] = "aprovada"
    return base


def rejeitado():
    base = pendente(analisado_por=2, analisado_em=AGORA, analise_observacao="Ruído")
    base["manutencao_status"] = "rejeitada"
    return base


def preparar(monkeypatch, funcao, retorno, existe=True):
    acao = AsyncMock(return_value=retorno)
    auditar = AsyncMock()
    notificar = AsyncMock()
    repositorio = main_module.repository
    monkeypatch.setattr(
        repositorio,
        "obter_alerta",
        AsyncMock(return_value=pendente() if existe else None),
    )
    monkeypatch.setattr(repositorio, funcao, acao)
    monkeypatch.setattr(repositorio, "registrar_auditoria", auditar)
    monkeypatch.setattr(main_module.manager, "broadcast_alertas", notificar)
    return acao, auditar, notificar


@pytest.mark.asyncio
async def test_listar_solicitacoes_pendentes(client_manutencao, monkeypatch):
    listar = AsyncMock(return_value=[pendente()])
    monkeypatch.setattr(
        main_module.repository, "listar_solicitacoes_manutencao", listar
    )

    response = await client_manutencao.get("/alertas/solicitacoes")

    assert response.status_code == 200
    assert response.json()[0]["manutencao_status"] == "pendente"
    assert listar.await_args.kwargs == {"status": "pendente", "limite": 100}


@pytest.mark.asyncio
async def test_operador_nao_ve_a_fila(client_operador):
    response = await client_operador.get("/alertas/solicitacoes")

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("acao", ["aprovar", "rejeitar"])
async def test_operador_nao_analisa(client_operador, acao):
    response = await client_operador.patch(
        f"/alertas/1/manutencao/{acao}", json={"observacao": "Tentativa"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_aprovar_audita_e_notifica(client_manutencao, monkeypatch):
    aprovar, auditar, notificar = preparar(
        monkeypatch, "aprovar_manutencao_alerta", aprovado()
    )

    response = await client_manutencao.patch(
        "/alertas/1/manutencao/aprovar",
        json={"data_agendada": "2026-11-25", "observacao": "Parada no turno 2"},
    )

    assert response.status_code == 200
    assert response.json()["manutencao_id"] == 7
    assert aprovar.await_args.args[1:] == (1, 4)
    assert aprovar.await_args.kwargs["data_agendada"] == date(2026, 11, 25)
    assert auditar.await_args.kwargs["acao"] == "APROVAR_MANUTENCAO_ML"
    assert notificar.await_args.args[0]["tipo"] == "manutencao_aprovada"


@pytest.mark.asyncio
async def test_rejeitar_audita_e_notifica(client_admin, monkeypatch):
    rejeitar, auditar, notificar = preparar(
        monkeypatch, "rejeitar_manutencao_alerta", rejeitado()
    )

    response = await client_admin.patch(
        "/alertas/1/manutencao/rejeitar", json={"observacao": "Ruído"}
    )

    assert response.status_code == 200
    assert rejeitar.await_args.args[1:] == (1, 2, "Ruído")
    assert auditar.await_args.kwargs["acao"] == "REJEITAR_MANUTENCAO_ML"
    assert notificar.await_args.args[0]["tipo"] == "manutencao_rejeitada"


@pytest.mark.asyncio
async def test_rejeitar_exige_motivo(client_admin):
    response = await client_admin.patch("/alertas/1/manutencao/rejeitar", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejeitar_nao_aceita_motivo_so_com_espacos(client_admin):
    response = await client_admin.patch(
        "/alertas/1/manutencao/rejeitar", json={"observacao": "      "}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_aprovar_nao_aceita_descricao_so_com_espacos(client_admin):
    response = await client_admin.patch(
        "/alertas/1/manutencao/aprovar", json={"descricao_servico": "        "}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_aprovar_limpa_os_textos(client_admin, monkeypatch):
    aprovar, _, _ = preparar(monkeypatch, "aprovar_manutencao_alerta", aprovado())

    response = await client_admin.patch(
        "/alertas/1/manutencao/aprovar",
        json={"descricao_servico": "  Trocar rolamento  ", "observacao": "   "},
    )

    assert response.status_code == 200
    assert aprovar.await_args.kwargs["descricao"] == "Trocar rolamento"
    assert aprovar.await_args.kwargs["observacao"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("acao", "funcao"),
    [
        ("aprovar", "aprovar_manutencao_alerta"),
        ("rejeitar", "rejeitar_manutencao_alerta"),
    ],
)
async def test_analise_sem_pendencia_e_conflito(
    client_admin, monkeypatch, acao, funcao
):
    _, auditar, notificar = preparar(monkeypatch, funcao, None)

    response = await client_admin.patch(
        f"/alertas/1/manutencao/{acao}", json={"observacao": "Motivo"}
    )

    assert response.status_code == 409
    auditar.assert_not_awaited()
    notificar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("acao", "funcao"),
    [
        ("aprovar", "aprovar_manutencao_alerta"),
        ("rejeitar", "rejeitar_manutencao_alerta"),
    ],
)
async def test_analise_de_alerta_inexistente(client_admin, monkeypatch, acao, funcao):
    executar, _, _ = preparar(monkeypatch, funcao, None, existe=False)

    response = await client_admin.patch(
        f"/alertas/99/manutencao/{acao}", json={"observacao": "Motivo"}
    )

    assert response.status_code == 404
    executar.assert_not_awaited()
