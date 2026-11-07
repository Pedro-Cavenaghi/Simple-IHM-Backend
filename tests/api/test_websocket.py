import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import auth
from app.main import app
from app.websocket_manager import manager


@pytest.fixture
def websocket_client():
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def limpar_conexoes_websocket():
    manager.machine_connections.clear()
    manager.global_connections.clear()
    yield
    manager.machine_connections.clear()                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
    manager.global_connections.clear()


def test_websocket_por_id_rejeita_conexao_sem_token(websocket_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with websocket_client.websocket_connect("/ws/telemetria/42"):
            pass

    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
    assert 42 not in manager.machine_connections


def test_websocket_por_id_rejeita_token_invalido(websocket_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with websocket_client.websocket_connect(
            "/ws/telemetria/42?token=token-invalido"
        ):
            pass

    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
    assert 42 not in manager.machine_connections


def test_websocket_por_id_conecta_maquina_com_token_valido(websocket_client):
    token = auth.criar_token_acesso(
        {"sub": "1", "perfil": "ADMIN"}
    )

    with websocket_client.websocket_connect(
        f"/ws/telemetria/42?token={token}"
    ) as websocket:
        assert 42 in manager.machine_connections
        assert len(manager.machine_connections[42]) == 1

        websocket.send_text("ping")

        assert 42 in manager.machine_connections

    assert 42 not in manager.machine_connections

    
def test_websocket_global_rejeita_conexao_sem_token(websocket_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with websocket_client.websocket_connect("/ws/telemetria"):
            pass

    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
    assert len(manager.global_connections) == 0


def test_websocket_global_conecta_com_token_valido(websocket_client):
    token = auth.criar_token_acesso(
        {"sub": "1", "perfil": "ADMIN"}
    )

    with websocket_client.websocket_connect(
        f"/ws/telemetria?token={token}"
    ) as websocket:
        assert len(manager.global_connections) == 1

        websocket.send_text("ping")

        assert len(manager.global_connections) == 1

    assert len(manager.global_connections) == 0

def test_websocket_global_rejeita_conexao_sem_token(websocket_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with websocket_client.websocket_connect("/ws/telemetria"):
            pass

    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
    assert len(manager.global_connections) == 0


def test_websocket_global_conecta_com_token_valido(websocket_client):
    token = auth.criar_token_acesso({
        "sub": "1",
        "perfil": "ADMIN"
    })

    with websocket_client.websocket_connect(
        f"/ws/telemetria?token={token}"
    ) as websocket:
        assert len(manager.global_connections) == 1

        websocket.send_text("ping")
        assert len(manager.global_connections) == 1

    assert len(manager.global_connections) == 0