from typing import List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Lista que armazena todas as conexões ativas do React
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Aceita a conexão do WebSocket e adiciona à lista."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a conexão quando o cliente desconecta."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Envia os dados em tempo real para TODOS os clientes React conectados."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Ignora se uma conexão específica caiu abruptamente
                pass


# Instância global compartilhada
manager = ConnectionManager()
