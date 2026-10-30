from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Conexões globais (usadas para seus testes / dashboards gerais)
        self.global_connections: List[WebSocket] = []
        # Conexões por máquina específica: { maquina_id: [WebSocket, ...] }
        self.machine_connections: Dict[int, List[WebSocket]] = {}

    # --- Métodos Globais (Testes) ---
    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.append(websocket)

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)

    # --- Métodos Por Máquina (Produção / App) ---
    async def connect_machine(self, websocket: WebSocket, maquina_id: int):
        await websocket.accept()
        if maquina_id not in self.machine_connections:
            self.machine_connections[maquina_id] = []
        self.machine_connections[maquina_id].append(websocket)

    def disconnect_machine(self, websocket: WebSocket, maquina_id: int):
        if (
            maquina_id in self.machine_connections
            and websocket in self.machine_connections[maquina_id]
        ):
            self.machine_connections[maquina_id].remove(websocket)
            if not self.machine_connections[maquina_id]:
                del self.machine_connections[maquina_id]

    # --- Transmissão (Broadcast) ---
    async def broadcast(self, data: dict):
        """Dispara a leitura tanto para os ouvintes da máquina quanto para conexões globais."""
        maquina_id = data.get("maquina_id")

        # 1. Envia para quem está ouvindo essa máquina específica
        if maquina_id and maquina_id in self.machine_connections:
            for connection in list(self.machine_connections[maquina_id]):
                try:
                    await connection.send_json(data)
                except Exception:
                    self.disconnect_machine(connection, maquina_id)

        # 2. Envia para as conexões globais de teste
        for connection in list(self.global_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect_global(connection)


# Instância global compartilhada
manager = ConnectionManager()
