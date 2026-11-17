"""Comunicação HTTP do simulador com a API, com buffer para quedas de rede."""

from collections import deque
from enum import Enum

import httpx


class ResultadoEnvio(str, Enum):
    ENVIADO = "enviado"
    BUFFER = "buffer"  # falha temporária: guardado para reenviar
    REJEITADO = "rejeitado"  # a API recusou (ex.: API Key ou validação)
    GERADO_OFFLINE = "gerado_offline"  # dataset gerado sem API (gerar_dataset.py)


class ClienteAPI:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 3.0,
        tamanho_buffer: int = 1000,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            transport=transport,
        )
        self.buffer: deque[dict] = deque(maxlen=tamanho_buffer)
        self.online: bool | None = None  # None = ainda não houve contato
        self.ultimo_erro: str | None = None

    async def fechar(self) -> None:
        await self._http.aclose()

    def _registrar_falha_de_rede(self, erro: Exception) -> None:
        self.online = False
        self.ultimo_erro = f"API indisponível ({type(erro).__name__})"

    def _registrar_resposta_de_erro(self, resposta: httpx.Response) -> None:
        self.online = True
        if resposta.status_code == 401:
            self.ultimo_erro = "API Key recusada (confira a variável API_KEY)"
        else:
            self.ultimo_erro = f"HTTP {resposta.status_code}: {resposta.text[:200]}"

    async def listar_maquinas(self) -> list[dict] | None:
        """Máquinas ativas e se estão em manutenção. None se não foi possível consultar."""
        try:
            resposta = await self._http.get("/dispositivos/maquinas")
        except httpx.HTTPError as erro:
            self._registrar_falha_de_rede(erro)
            return None

        if resposta.status_code != 200:
            self._registrar_resposta_de_erro(resposta)
            return None

        self.online = True
        self.ultimo_erro = None
        return resposta.json()

    async def _postar(self, leitura: dict) -> ResultadoEnvio:
        try:
            resposta = await self._http.post("/enviar-dados", json=leitura)
        except httpx.HTTPError as erro:
            self._registrar_falha_de_rede(erro)
            return ResultadoEnvio.BUFFER

        if resposta.status_code == 200:
            self.online = True
            self.ultimo_erro = None
            return ResultadoEnvio.ENVIADO

        self._registrar_resposta_de_erro(resposta)
        # Erro no servidor (ex.: banco fora) é temporário; erro do cliente não adianta repetir
        if resposta.status_code >= 500:
            return ResultadoEnvio.BUFFER
        return ResultadoEnvio.REJEITADO

    async def enviar(self, leitura: dict) -> ResultadoEnvio:
        if not self.buffer:
            resultado = await self._postar(leitura)
            if resultado == ResultadoEnvio.BUFFER:
                self.buffer.append(leitura)
            return resultado

        # Há leituras pendentes: entra na fila para chegar em ordem cronológica
        self.buffer.append(leitura)
        await self.descarregar_buffer()
        if any(item is leitura for item in self.buffer):
            return ResultadoEnvio.BUFFER
        return ResultadoEnvio.ENVIADO

    async def descarregar_buffer(self) -> int:
        """Reenvia as leituras acumuladas, na ordem. Retorna quantas foram entregues."""
        entregues = 0
        while self.buffer:
            leitura = self.buffer.popleft()
            resultado = await self._postar(leitura)
            if resultado == ResultadoEnvio.BUFFER:
                self.buffer.appendleft(leitura)
                break
            if resultado == ResultadoEnvio.ENVIADO:
                entregues += 1
        return entregues
