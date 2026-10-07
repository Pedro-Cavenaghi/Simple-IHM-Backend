from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_agendar_manutencao(client, monkeypatch):
    mock_repository = AsyncMock(return_value=1)

    monkeypatch.setattr(
        main_module.repository,
        "agendar_manutencao",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "descricao_servico": "Troca preventiva de rolamento",
        "data_agendada": "2026-10-15",
        "tipo_manutencao": "Preventiva",
    }

    response = await client.post(
        "/manutencoes",
        json=payload,
    )

    dados = response.json()

    assert response.status_code == 201
    assert dados["id"] == 1
    assert dados["maquina_id"] == 1
    assert dados["descricao_servico"] == "Troca preventiva de rolamento"
    assert dados["tipo_manutencao"] == "Preventiva"
    assert dados["concluida"] is False
    assert dados["funcionario_id"] is None

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_agendar_manutencao_com_erro(client, monkeypatch):
    mock_repository = AsyncMock(return_value=None)

    monkeypatch.setattr(
        main_module.repository,
        "agendar_manutencao",
        mock_repository,
    )

    payload = {
        "maquina_id": 999,
        "descricao_servico": "Troca preventiva de rolamento",
        "data_agendada": "2026-10-15",
        "tipo_manutencao": "Preventiva",
    }

    response = await client.post(
        "/manutencoes",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Erro ao agendar manutenção. "
        "Verifique se o maquina_id informado existe."
    )

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_agendar_manutencao_tipo_invalido(client, monkeypatch):
    mock_repository = AsyncMock(return_value=1)

    monkeypatch.setattr(
        main_module.repository,
        "agendar_manutencao",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "descricao_servico": "Troca preventiva de rolamento",
        "data_agendada": "2026-10-15",
        "tipo_manutencao": "Corretiva",
    }

    response = await client.post(
        "/manutencoes",
        json=payload,
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_agendar_manutencao_descricao_curta(client, monkeypatch):
    mock_repository = AsyncMock(return_value=1)

    monkeypatch.setattr(
        main_module.repository,
        "agendar_manutencao",
        mock_repository,
    )

    payload = {
        "maquina_id": 1,
        "descricao_servico": "abc",
        "data_agendada": "2026-10-15",
        "tipo_manutencao": "Preventiva",
    }

    response = await client.post(
        "/manutencoes",
        json=payload,
    )

    assert response.status_code == 422

    mock_repository.assert_not_awaited()


@pytest.mark.asyncio
async def test_listar_manutencoes(client, monkeypatch):
    manutencoes = [
        {
            "id": 1,
            "maquina_id": 1,
            "tag_maquina": "INJ-01",
            "nome_maquina": "Injetora 01",
            "descricao_servico": "Troca preventiva de rolamento",
            "data_agendada": date(2026, 10, 15),
            "concluida": False,
            "data_conclusao_real": None,
            "funcionario_id": None,
            "nome_funcionario": None,
            "tipo_manutencao": "Preventiva",
        }
    ]

    mock_repository = AsyncMock(return_value=manutencoes)

    monkeypatch.setattr(
        main_module.repository,
        "listar_manutencoes_detalhadas",
        mock_repository,
    )

    response = await client.get("/manutencoes")

    dados = response.json()

    assert response.status_code == 200
    assert len(dados) == 1
    assert dados[0]["id"] == 1
    assert dados[0]["maquina_id"] == 1
    assert dados[0]["tipo_manutencao"] == "Preventiva"
    assert dados[0]["concluida"] is False

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_obter_manutencao_por_id(client, monkeypatch):
    manutencao = {
        "id": 1,
        "maquina_id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "descricao_servico": "Troca preventiva de rolamento",
        "data_agendada": date(2026, 10, 15),
        "concluida": False,
        "data_conclusao_real": None,
        "funcionario_id": None,
        "nome_funcionario": None,
        "tipo_manutencao": "Preventiva",
    }

    mock_repository = AsyncMock(return_value=manutencao)

    monkeypatch.setattr(
        main_module.repository,
        "obter_manutencao_por_id",
        mock_repository,
    )

    response = await client.get("/manutencoes/1")

    dados = response.json()

    assert response.status_code == 200
    assert dados["id"] == 1
    assert dados["tag_maquina"] == "INJ-01"
    assert dados["tipo_manutencao"] == "Preventiva"

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_obter_manutencao_inexistente(client, monkeypatch):
    mock_repository = AsyncMock(return_value=None)

    monkeypatch.setattr(
        main_module.repository,
        "obter_manutencao_por_id",
        mock_repository,
    )

    response = await client.get("/manutencoes/999")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Ordem de manutenção não encontrada."
    )

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_atualizar_manutencao(client, monkeypatch):
    manutencao_atualizada = {
        "id": 1,
        "maquina_id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "descricao_servico": "Nova manutenção preventiva",
        "data_agendada": date(2026, 10, 20),
        "concluida": False,
        "data_conclusao_real": None,
        "funcionario_id": None,
        "nome_funcionario": None,
        "tipo_manutencao": "Preditiva",
    }

    mock_atualizar = AsyncMock(return_value=True)
    mock_obter = AsyncMock(return_value=manutencao_atualizada)

    monkeypatch.setattr(
        main_module.repository,
        "atualizar_dados_manutencao",
        mock_atualizar,
    )

    monkeypatch.setattr(
        main_module.repository,
        "obter_manutencao_por_id",
        mock_obter,
    )

    payload = {
        "descricao_servico": "Nova manutenção preventiva",
        "data_agendada": "2026-10-20",
        "tipo_manutencao": "Preditiva",
    }

    response = await client.put(
        "/manutencoes/1",
        json=payload,
    )

    dados = response.json()

    assert response.status_code == 200
    assert dados["id"] == 1
    assert dados["descricao_servico"] == "Nova manutenção preventiva"
    assert dados["tipo_manutencao"] == "Preditiva"

    mock_atualizar.assert_awaited_once()
    mock_obter.assert_awaited_once()


@pytest.mark.asyncio
async def test_atualizar_manutencao_com_erro(client, monkeypatch):
    mock_repository = AsyncMock(return_value=False)

    monkeypatch.setattr(
        main_module.repository,
        "atualizar_dados_manutencao",
        mock_repository,
    )

    payload = {
        "descricao_servico": "Nova manutenção preventiva",
        "data_agendada": "2026-10-20",
        "tipo_manutencao": "Preventiva",
    }

    response = await client.put(
        "/manutencoes/999",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Não foi possível atualizar. "
        "A ordem pode não existir ou já está CONCLUÍDA."
    )

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_concluir_manutencao(client, monkeypatch):
    manutencao_concluida = {
        "id": 1,
        "maquina_id": 1,
        "tag_maquina": "INJ-01",
        "nome_maquina": "Injetora 01",
        "descricao_servico": "Troca preventiva de rolamento",
        "data_agendada": date(2026, 10, 15),
        "concluida": True,
        "data_conclusao_real": datetime(2026, 10, 15, 15, 30),
        "funcionario_id": 2,
        "nome_funcionario": "Carlos Técnico",
        "tipo_manutencao": "Preventiva",
    }

    mock_concluir = AsyncMock(return_value=True)
    mock_obter = AsyncMock(return_value=manutencao_concluida)

    monkeypatch.setattr(
        main_module.repository,
        "concluir_ordem_manutencao",
        mock_concluir,
    )

    monkeypatch.setattr(
        main_module.repository,
        "obter_manutencao_por_id",
        mock_obter,
    )

    response = await client.patch(
        "/manutencoes/1/concluir",
        json={
            "funcionario_id": 2,
        },
    )

    dados = response.json()

    assert response.status_code == 200
    assert dados["id"] == 1
    assert dados["concluida"] is True
    assert dados["funcionario_id"] == 2
    assert dados["nome_funcionario"] == "Carlos Técnico"

    mock_concluir.assert_awaited_once()
    mock_obter.assert_awaited_once()


@pytest.mark.asyncio
async def test_concluir_manutencao_com_erro(client, monkeypatch):
    mock_repository = AsyncMock(return_value=False)

    monkeypatch.setattr(
        main_module.repository,
        "concluir_ordem_manutencao",
        mock_repository,
    )

    response = await client.patch(
        "/manutencoes/999/concluir",
        json={
            "funcionario_id": 2,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Falha ao encerrar ordem. "
        "Verifique se o técnico existe ou se a ordem já foi fechada."
    )

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_deletar_manutencao(client, monkeypatch):
    mock_repository = AsyncMock(return_value=True)

    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_manutencao",
        mock_repository,
    )

    response = await client.delete("/manutencoes/1")

    dados = response.json()

    assert response.status_code == 200
    assert dados["status"] == "Sucesso"
    assert dados["mensagem"] == "Ordem 1 desativada logicamente."

    mock_repository.assert_awaited_once()


@pytest.mark.asyncio
async def test_deletar_manutencao_com_erro(client, monkeypatch):
    mock_repository = AsyncMock(return_value=False)

    monkeypatch.setattr(
        main_module.repository,
        "soft_delete_manutencao",
        mock_repository,
    )

    response = await client.delete("/manutencoes/999")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Não é possível remover. "
        "A ordem pode não existir, já foi concluída ou já foi excluída."
    )

    mock_repository.assert_awaited_once()