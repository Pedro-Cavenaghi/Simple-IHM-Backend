import json

import httpx
import pytest

from simulador.cliente_api import ClienteAPI, ResultadoEnvio

LEITURA = {"maquina_id": 1, "status_atual": "Ativa"}


def criar_cliente(handler) -> ClienteAPI:
    return ClienteAPI(
        "http://api.teste",
        "chave-teste",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_envia_leitura_com_api_key():
    recebidas = []

    def handler(request: httpx.Request):
        recebidas.append(request)
        return httpx.Response(200, json={"status": "Sucesso"})

    cliente = criar_cliente(handler)

    assert await cliente.enviar(LEITURA) == ResultadoEnvio.ENVIADO
    assert recebidas[0].url.path == "/enviar-dados"
    assert recebidas[0].headers["X-API-Key"] == "chave-teste"
    assert cliente.online is True
    assert cliente.ultimo_erro is None

    await cliente.fechar()


@pytest.mark.asyncio
async def test_falha_de_rede_guarda_no_buffer():
    def handler(request):
        raise httpx.ConnectError("sem rede")

    cliente = criar_cliente(handler)

    assert await cliente.enviar(LEITURA) == ResultadoEnvio.BUFFER
    assert list(cliente.buffer) == [LEITURA]
    assert cliente.online is False

    await cliente.fechar()


@pytest.mark.asyncio
async def test_erro_500_guarda_no_buffer():
    cliente = criar_cliente(lambda request: httpx.Response(500, json={}))

    assert await cliente.enviar(LEITURA) == ResultadoEnvio.BUFFER
    assert len(cliente.buffer) == 1

    await cliente.fechar()


@pytest.mark.asyncio
async def test_api_key_recusada_nao_vai_para_o_buffer():
    cliente = criar_cliente(lambda request: httpx.Response(401, json={}))

    assert await cliente.enviar(LEITURA) == ResultadoEnvio.REJEITADO
    assert len(cliente.buffer) == 0
    assert "API Key" in cliente.ultimo_erro

    await cliente.fechar()


@pytest.mark.asyncio
async def test_buffer_e_descarregado_em_ordem_quando_a_api_volta():
    online = {"valor": False}
    entregues = []

    def handler(request: httpx.Request):
        if not online["valor"]:
            raise httpx.ConnectError("sem rede")
        entregues.append(json.loads(request.content)["n"])
        return httpx.Response(200, json={})

    cliente = criar_cliente(handler)

    await cliente.enviar({"maquina_id": 1, "n": 1})
    await cliente.enviar({"maquina_id": 1, "n": 2})

    # Ainda offline: a nova leitura entra no fim da fila
    assert await cliente.enviar({"maquina_id": 1, "n": 3}) == ResultadoEnvio.BUFFER
    assert [item["n"] for item in cliente.buffer] == [1, 2, 3]

    online["valor"] = True

    assert await cliente.enviar({"maquina_id": 1, "n": 4}) == ResultadoEnvio.ENVIADO
    assert len(cliente.buffer) == 0
    assert entregues == [1, 2, 3, 4]

    await cliente.fechar()


@pytest.mark.asyncio
async def test_leitura_rejeitada_no_buffer_e_descartada():
    respostas = iter(
        [httpx.ConnectError("sem rede"), httpx.Response(422), httpx.Response(200)]
    )

    def handler(request):
        resposta = next(respostas)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    cliente = criar_cliente(handler)
    await cliente.enviar({"n": 1})

    assert await cliente.enviar({"n": 2}) == ResultadoEnvio.ENVIADO
    assert len(cliente.buffer) == 0

    await cliente.fechar()


@pytest.mark.asyncio
async def test_listar_maquinas():
    maquinas = [{"id": 1, "tag_maquina": "CNC-01", "em_manutencao": False}]

    def handler(request: httpx.Request):
        assert request.url.path == "/dispositivos/maquinas"
        return httpx.Response(200, json=maquinas)

    cliente = criar_cliente(handler)

    assert await cliente.listar_maquinas() == maquinas

    await cliente.fechar()


@pytest.mark.asyncio
async def test_listar_maquinas_com_falha_retorna_none():
    def handler(request):
        raise httpx.ConnectError("sem rede")

    cliente = criar_cliente(handler)

    assert await cliente.listar_maquinas() is None
    assert cliente.online is False

    await cliente.fechar()


@pytest.mark.asyncio
async def test_listar_maquinas_com_erro_http_retorna_none():
    cliente = criar_cliente(lambda request: httpx.Response(401, json={}))

    assert await cliente.listar_maquinas() is None
    assert "API Key" in cliente.ultimo_erro

    await cliente.fechar()
