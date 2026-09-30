import asyncio
import random
import httpx
import os

# Rotas da API
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

API_ENVIAR_DADOS = f"{BASE_URL}/enviar-dados"
API_MANUTENCOES = f"{BASE_URL}/manutencoes"

CONFIG_MAQUINAS = {
    1: {"tag": "CNC-01", "corrente_media": 15.5, "vibracao_media": 2.1},
    2: {"tag": "INJ-01", "corrente_media": 32.0, "vibracao_media": 5.8},
    3: {"tag": "PRE-01", "corrente_media": 8.0, "vibracao_media": 0.4},
}


ESTADOS_POSSIVEIS = ["Ativa", "Inativa", "Desligada", "Manutenção"]

# Buffer em memória para salvar dados caso a rede caia
BUFFER_LOCAL = []


async def checar_se_esta_em_manutencao(
    client: httpx.AsyncClient, maquina_id: int
) -> bool:
    """
    Consulta a API central para verificar se existe alguma Ordem de Serviço
    aberta e não concluída para esta máquina.
    """
    try:
        response = await client.get(API_MANUTENCOES, timeout=1.5)
        if response.status_code == 200:
            manutencoes = response.json()

            for os in manutencoes:
                if os.get("maquina_id") == maquina_id and os.get("concluida") is False:
                    return True
    except Exception:
        pass
    return False


def gerar_leitura_fake_otimizada(status_travado: bool, maquina_id: int) -> dict:
    """
    Gera a leitura dos sensores de forma síncrona, leve e estritamente
    dentro das restrições matemáticas impostas pelo Pydantic (LeituraSensor).
    """
    cfg = CONFIG_MAQUINAS[maquina_id]

    if status_travado:
        status = "Manutenção"
    else:
        # Sorteia apenas os estados normais de produção (Manutenção controlada logicamente pela API)
        status = random.choices(ESTADOS_POSSIVEIS, weights=[90, 8, 2, 0])[0]

    # Comportamento elétrico e mecânico baseado no estado de operação
    if status in ("Manutenção", "Desligada"):
        corrente, vibracao, potencia, frequencia = 0.0, 0.0, 0.0, 0.0
        tensao = (
            random.gauss(220.0, 0.5)
            if status == "Manutenção"
            else random.gauss(220.0, 1.0)
        )
    elif status == "Inativa":
        corrente = random.gauss(0.5, 0.05)
        vibracao = random.gauss(0.1, 0.02)
        tensao = random.gauss(220.0, 1.5)
        potencia = corrente * tensao * 0.9
        frequencia = random.gauss(60.0, 0.05)
    else:
        # Máquina Operando em Carga
        corrente = random.gauss(cfg["corrente_media"], cfg["corrente_media"] * 0.1)
        vibracao = random.gauss(cfg["vibracao_media"], cfg["vibracao_media"] * 0.15)
        tensao = random.gauss(220.0, 2.0)
        potencia = corrente * tensao * 0.85
        frequencia = random.gauss(60.0, 0.2)

    # GAPS DEFENSIVOS
    corrente = max(0.0, corrente)
    vibracao = max(0.0, vibracao)
    potencia = max(0.0, potencia)
    tensao = max(0.0, min(250.0, tensao))
    frequencia = max(0.0, min(100.0, frequencia))

    return {
        "maquina_id": maquina_id,
        "vibracao_rms": round(vibracao, 2),
        "corrente_ampere": round(corrente, 2),
        "tensao_volt": round(tensao, 1),
        "potencia_watt": round(potencia, 2),
        "frequencia_hz": round(frequencia, 2),
        "status_atual": status,
    }


async def enviar_dado(client: httpx.AsyncClient, payload: dict) -> bool:
    """Dispara a telemetria para a API. Se houver falha física de rede, joga para o buffer local."""
    tag = CONFIG_MAQUINAS[payload["maquina_id"]]["tag"]
    try:
        response = await client.post(API_ENVIAR_DADOS, json=payload, timeout=2.0)
        if response.status_code in (200, 201):
            print(
                f"[Sucesso] {tag} -> Status: {payload['status_atual']} | {payload['corrente_ampere']} A"
            )
            return True
        else:
            print(
                f"[Erro API] Status {response.status_code} para {tag}. Payload rejeitado pela validação."
            )
            return False
    except (httpx.ConnectError, httpx.TimeoutException):
        print(f"[FALHA DE REDE] API indisponível. {tag} salvo no buffer local.")

    BUFFER_LOCAL.append(payload)
    return False


async def processar_buffer(client: httpx.AsyncClient):
    """Tenta descarregar de forma ordenada os dados armazenados temporariamente na memória."""
    if not BUFFER_LOCAL:
        return

    print(f"\n [Buffer] Tentando descarregar {len(BUFFER_LOCAL)} pacotes acumulados...")
    itens_para_enviar = list(BUFFER_LOCAL)
    BUFFER_LOCAL.clear()

    for payload in itens_para_enviar:
        try:
            response = await client.post(API_ENVIAR_DADOS, json=payload, timeout=2.0)
            if response.status_code in (200, 201):
                print(
                    f" [Buffer -> Sucesso] Dado retroativo da máquina {payload['maquina_id']} enviado."
                )
            else:
                print(
                    f" [Buffer -> Descartado] Erro HTTP {response.status_code} no dado acumulado."
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            BUFFER_LOCAL.append(payload)
            break


async def ciclo_maquina(maquina_id: int, intervalo: int):
    """Loop isolado por máquina que gerencia a cadência de envio e o cache lógico de O.S."""
    async with httpx.AsyncClient() as client:
        esta_em_manutencao = False
        contador_ciclos = 0

        CICLOS_PARA_CHECAR = 15

        while True:
            if contador_ciclos % CICLOS_PARA_CHECAR == 0 or esta_em_manutencao:
                esta_em_manutencao = await checar_se_esta_em_manutencao(
                    client, maquina_id
                )
                contador_ciclos = 0

            payload = gerar_leitura_fake_otimizada(
                status_travado=esta_em_manutencao, maquina_id=maquina_id
            )

            await enviar_dado(client, payload)
            await processar_buffer(client)

            contador_ciclos += 1
            await asyncio.sleep(intervalo)


async def main():
    print("=== Simulador Industrial Assíncrono Avançado ===")
    print(
        f"Destino Telemetria: {API_ENVIAR_DADOS} | Escuta Manutenções: {API_MANUTENCOES}\n"
    )

    tarefas = [
        ciclo_maquina(maquina_id=1, intervalo=2),
        ciclo_maquina(maquina_id=2, intervalo=2),
        ciclo_maquina(maquina_id=3, intervalo=2),
    ]

    await asyncio.gather(*tarefas)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSimulador encerrado pelo usuário.")
