from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as main_module
from app import auth
from app.main import app
from app.websocket_manager import manager

AGORA = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def alerta(**extra):
    base = {
        "id": 1,
        "maquina_id": 3,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora",
        "diagnostico": "desgaste_rolamento",
        "confianca": 0.92,
        "pontuacao": 0.31,
        "severidade": "media",
        "mensagem": "Provável desgaste de rolamento (confiança de 92%).",
        "minutos_ate_limite": 4.5,
        "criado_em": AGORA,
        "atualizado_em": AGORA,
        "encerrado_em": None,
        "reconhecido_em": None,
        "reconhecido_por": None,
        "reconhecido_por_nome": None,
        "manutencao_id": None,
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def limpar_canal_de_alertas():
    manager.alert_connections.clear()
    yield
    manager.alert_connections.clear()


# ---------- REST ----------


@pytest.mark.asyncio
async def test_listar_alertas_com_filtros(client_operador, monkeypatch):
    listar = AsyncMock(return_value=[alerta()])
    monkeypatch.setattr(main_module.repository, "listar_alertas", listar)

    response = await client_operador.get(
        "/alertas", params={"maquina_id": 3, "apenas_abertos": True, "limite": 10}
    )

    assert response.status_code == 200
    assert response.json()[0]["diagnostico"] == "desgaste_rolamento"
    _, kwargs = listar.await_args
    assert kwargs == {"maquina_id": 3, "apenas_abertos": True, "limite": 10}


@pytest.mark.asyncio
async def test_listar_alertas_exige_login(client):
    response = await client.get("/alertas")

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_obter_alerta(client_manutencao, monkeypatch):
    monkeypatch.setattr(
        main_module.repository, "obter_alerta", AsyncMock(return_value=alerta())
    )

    response = await client_manutencao.get("/alertas/1")

    assert response.status_code == 200
    assert response.json()["minutos_ate_limite"] == 4.5


@pytest.mark.asyncio
async def test_obter_alerta_inexistente(client_operador, monkeypatch):
    monkeypatch.setattr(
        main_module.repository, "obter_alerta", AsyncMock(return_value=None)
    )

    response = await client_operador.get("/alertas/99")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reconhecer_alerta_audita_e_notifica(client_operador, monkeypatch):
    reconhecido = alerta(
        reconhecido_em=AGORA, reconhecido_por=3, reconhecido_por_nome="Operador Teste"
    )
    monkeypatch.setattr(
        main_module.repository, "obter_alerta", AsyncMock(return_value=alerta())
    )
    reconhecer = AsyncMock(return_value=reconhecido)
    auditar = AsyncMock()
    notificar = AsyncMock()
    monkeypatch.setattr(main_module.repository, "reconhecer_alerta", reconhecer)
    monkeypatch.setattr(main_module.repository, "registrar_auditoria", auditar)
    monkeypatch.setattr(main_module.manager, "broadcast_alertas", notificar)

    response = await client_operador.patch("/alertas/1/reconhecer")

    assert response.status_code == 200
    assert response.json()["reconhecido_por_nome"] == "Operador Teste"
    reconhecer.assert_awaited_once()
    assert reconhecer.await_args.args[1:] == (1, 3)
    assert auditar.await_args.kwargs["acao"] == "RECONHECER_ALERTA"
    mensagem = notificar.await_args.args[0]
    assert mensagem["tipo"] == "alerta_reconhecido"
    assert mensagem["alerta"]["reconhecido_em"].startswith("2026-11-17")


@pytest.mark.asyncio
async def test_reconhecer_alerta_inexistente(client_operador, monkeypatch):
    monkeypatch.setattr(
        main_module.repository, "obter_alerta", AsyncMock(return_value=None)
    )

    response = await client_operador.patch("/alertas/99/reconhecer")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reconhecer_alerta_duas_vezes(client_operador, monkeypatch):
    monkeypatch.setattr(
        main_module.repository, "obter_alerta", AsyncMock(return_value=alerta())
    )
    monkeypatch.setattr(
        main_module.repository, "reconhecer_alerta", AsyncMock(return_value=None)
    )

    response = await client_operador.patch("/alertas/1/reconhecer")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_status_do_ml_negado_para_operador(client_operador):
    response = await client_operador.get("/ml/status")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_status_do_ml_para_admin(client_admin):
    response = await client_admin.get("/ml/status")

    assert response.status_code == 200
    assert "habilitado" in response.json()


# ---------- telemetria aciona o monitor ----------


@pytest.mark.asyncio
async def test_enviar_dados_agenda_o_monitor(client, monkeypatch):
    monkeypatch.setattr(
        main_module.repository, "salvar_leitura", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(main_module.manager, "broadcast", AsyncMock())
    processar = AsyncMock()
    monkeypatch.setattr(main_module.monitor, "processar", processar)
    leitura = {
        "maquina_id": 1,
        "vibracao_rms": 1.5,
        "corrente_ampere": 10.0,
        "tensao_volt": 220.0,
        "potencia_watt": 2000.0,
        "frequencia_hz": 60.0,
        "status_atual": "Ativa",
    }

    response = await client.post(
        "/enviar-dados", json=leitura, headers={"X-API-Key": auth.API_KEY}
    )

    assert response.status_code == 200
    processar.assert_awaited_once_with(leitura)


@pytest.mark.asyncio
async def test_notificar_alerta_serializa_para_o_websocket(monkeypatch):
    enviar = AsyncMock()
    monkeypatch.setattr(main_module.manager, "broadcast_alertas", enviar)

    await main_module.notificar_alerta("alerta_criado", alerta())

    mensagem = enviar.await_args.args[0]
    assert mensagem["tipo"] == "alerta_criado"
    assert mensagem["alerta"]["criado_em"] == "2026-11-17T12:00:00Z"


# ---------- WebSocket ----------


@pytest.fixture
def websocket_client():
    cliente = TestClient(app)
    yield cliente
    cliente.close()


def test_websocket_alertas_rejeita_sem_token(websocket_client):
    with pytest.raises(WebSocketDisconnect) as erro:
        with websocket_client.websocket_connect("/ws/alertas"):
            pass

    assert erro.value.code == status.WS_1008_POLICY_VIOLATION
    assert manager.alert_connections == []


def test_websocket_alertas_rejeita_token_invalido(websocket_client):
    with pytest.raises(WebSocketDisconnect):
        with websocket_client.websocket_connect("/ws/alertas?token=invalido"):
            pass


def test_websocket_alertas_recebe_broadcast(websocket_client):
    token = auth.criar_token_acesso({"sub": "1", "perfil": "OPERADOR"})

    with websocket_client.websocket_connect(f"/ws/alertas?token={token}") as ws:
        assert len(manager.alert_connections) == 1
        ws.portal.call(
            manager.broadcast_alertas, {"tipo": "alerta_criado", "alerta": {"id": 1}}
        )
        assert ws.receive_json() == {"tipo": "alerta_criado", "alerta": {"id": 1}}

    assert manager.alert_connections == []
