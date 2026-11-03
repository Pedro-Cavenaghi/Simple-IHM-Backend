
from unittest.mock import AsyncMock

import pytest

from app.websocket_manager import ConnectionManager


@pytest.fixture
def connection_manager():
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_global_aceita_e_adiciona_conexao(connection_manager):
    websocket = AsyncMock()

    await connection_manager.connect_global(websocket)

    websocket.accept.assert_awaited_once()
    assert websocket in connection_manager.global_connections


def test_disconnect_global_remove_conexao(connection_manager):
    websocket = AsyncMock()
    connection_manager.global_connections.append(websocket)

    connection_manager.disconnect_global(websocket)

    assert websocket not in connection_manager.global_connections


def test_disconnect_global_ignora_conexao_inexistente(connection_manager):
    websocket = AsyncMock()

    connection_manager.disconnect_global(websocket)

    assert connection_manager.global_connections == []


@pytest.mark.asyncio
async def test_connect_machine_cria_lista_e_adiciona_conexao(
    connection_manager,
):
    websocket = AsyncMock()

    await connection_manager.connect_machine(websocket, 42)

    websocket.accept.assert_awaited_once()
    assert 42 in connection_manager.machine_connections
    assert websocket in connection_manager.machine_connections[42]


@pytest.mark.asyncio
async def test_connect_machine_adiciona_multiplas_conexoes(
    connection_manager,
):
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()

    await connection_manager.connect_machine(websocket1, 42)
    await connection_manager.connect_machine(websocket2, 42)

    assert len(connection_manager.machine_connections[42]) == 2


def test_disconnect_machine_remove_conexao_e_preserva_as_outras(
    connection_manager,
):
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()

    connection_manager.machine_connections[42] = [
        websocket1,
        websocket2,
    ]

    connection_manager.disconnect_machine(websocket1, 42)

    assert connection_manager.machine_connections[42] == [websocket2]


def test_disconnect_machine_remove_maquina_sem_conexoes(
    connection_manager,
):
    websocket = AsyncMock()
    connection_manager.machine_connections[42] = [websocket]

    connection_manager.disconnect_machine(websocket, 42)

    assert 42 not in connection_manager.machine_connections


def test_disconnect_machine_ignora_conexao_inexistente(
    connection_manager,
):
    websocket = AsyncMock()
    outra_conexao = AsyncMock()

    connection_manager.machine_connections[42] = [outra_conexao]

    connection_manager.disconnect_machine(websocket, 42)
    connection_manager.disconnect_machine(websocket, 99)

    assert connection_manager.machine_connections[42] == [outra_conexao]


@pytest.mark.asyncio
async def test_broadcast_envia_para_maquina_e_conexoes_globais(
    connection_manager,
):
    websocket_maquina = AsyncMock()
    websocket_global = AsyncMock()

    connection_manager.machine_connections[42] = [websocket_maquina]
    connection_manager.global_connections.append(websocket_global)

    data = {"maquina_id": 42, "temperatura": 35.5}

    await connection_manager.broadcast(data)

    websocket_maquina.send_json.assert_awaited_once_with(data)
    websocket_global.send_json.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_broadcast_envia_para_globais_sem_maquina_id(
    connection_manager,
):
    websocket_global = AsyncMock()
    connection_manager.global_connections.append(websocket_global)

    data = {"temperatura": 35.5}

    await connection_manager.broadcast(data)

    websocket_global.send_json.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_broadcast_ignora_maquina_sem_conexoes(
    connection_manager,
):
    websocket_global = AsyncMock()
    connection_manager.global_connections.append(websocket_global)

    data = {"maquina_id": 99, "temperatura": 35.5}

    await connection_manager.broadcast(data)

    websocket_global.send_json.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_broadcast_remove_conexao_de_maquina_com_erro(
    connection_manager,
):
    websocket_maquina = AsyncMock()
    websocket_global = AsyncMock()

    websocket_maquina.send_json.side_effect = Exception(
        "Conexão encerrada"
    )

    connection_manager.machine_connections[42] = [websocket_maquina]
    connection_manager.global_connections.append(websocket_global)

    data = {"maquina_id": 42, "temperatura": 35.5}

    await connection_manager.broadcast(data)

    assert 42 not in connection_manager.machine_connections
    websocket_global.send_json.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_broadcast_remove_conexao_global_com_erro(
    connection_manager,
):
    websocket_global = AsyncMock()
    websocket_global.send_json.side_effect = Exception(
        "Conexão encerrada"
    )

    connection_manager.global_connections.append(websocket_global)

    await connection_manager.broadcast({"temperatura": 35.5})

    assert websocket_global not in connection_manager.global_connections
