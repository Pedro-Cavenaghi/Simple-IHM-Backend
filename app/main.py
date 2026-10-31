import os
import warnings
from contextlib import asynccontextmanager
from datetime import date, datetime

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from passlib.context import CryptContext
from pydantic import BaseModel

import app.repository as repository
from app import auth
from app.database import Database, get_db

# Importação do gerenciador de WebSockets
from app.websocket_manager import manager

# Importações internas dos modelos
from .models import (
    AuditLogResponse,
    FuncionarioCreate,
    FuncionarioResponse,
    FuncionarioUpdate,
    LeituraSensor,
    LogMaquinaResponse,
    ManutencaoPreventivaCreate,
    ManutencaoPreventivaDetalhadaResponse,
    ManutencaoPreventivaResponse,
    ManutencaoPreventivaUpdate,
    MaquinaCreate,
    MaquinaResponse,
    MaquinaStatusResponse,
    MaquinaUpdate,
)

warnings.filterwarnings("ignore", category=UserWarning, module="passlib")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: str
    senha: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database.connect()
    print("\n" + "=" * 60)
    print("🚀 API DO ECOSSISTEMA IoT INDUSTRIAL ONLINE!")
    print("🔗 Local:        http://127.0.0.1:8000")
    print("📖 Documentação: http://127.0.0.1:8000/docs")
    print("=" * 60 + "\n")
    yield
    await Database.disconnect()


app = FastAPI(
    title="Simple IHM API",
    description="Ecossistema IoT para Automação Industrial - Fatec",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Geral"])
async def root():
    return {"mensagem": "API Simple IHM Ativa (Assíncrona)"}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_favicon_url="/favicon.ico",
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(BASE_DIR, "..", "favicon.ico"))


# ==========================================
# WEBSOCKET & TELEMETRIA IOT EM TEMPO REAL
# ==========================================


@app.websocket("/ws/telemetria")
async def websocket_telemetria_global(
    websocket: WebSocket, token: str | None = Query(None)
):
    if not token or not auth.validar_token_jwt_simples(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        manager.disconnect_global(websocket)


@app.websocket("/ws/telemetria/{maquina_id}")
async def websocket_telemetria_por_id(
    websocket: WebSocket, maquina_id: int, token: str | None = Query(None)
):
    if not token or not auth.validar_token_jwt_simples(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_machine(websocket, maquina_id)
    try:
        while True:
            await websocket.receive_text()  # Mantém o heartbeat / ping-pong
    except Exception:
        manager.disconnect_machine(websocket, maquina_id)


@app.post("/enviar-dados", status_code=status.HTTP_200_OK, tags=["Telemetria IoT"])
async def receber_dados(
    leitura: LeituraSensor,
    conn: asyncpg.Connection = Depends(get_db),
    _: str = Depends(
        auth.verificar_api_key
    ),  # Trava o endpoint exigindo X-API-Key da ESP32
):
    """Endpoint consumido pela ESP32 / Simulador para gravar os logs históricos no

    PostgreSQL e transmitir as atualizações instantaneamente via WebSocket para
    o React.
    """
    dados_leitura = leitura.model_dump()

    # 1. Salva a leitura no banco de dados
    sucesso = await repository.salvar_leitura(conn, dados_leitura)

    if sucesso:
        # 2. Transmite os novos dados recebidos via WebSocket Broadcast para os navegadores
        await manager.broadcast(dados_leitura)
        return {
            "status": "Sucesso",
            "mensagem": "Dados gravados e transmitidos em tempo real",
        }

    raise HTTPException(
        status_code=500, detail="Erro ao gravar os dados de telemetria no banco"
    )


@app.get(
    "/status-maquinas",
    response_model=list[MaquinaStatusResponse],
    tags=["Telemetria IoT"],
)
async def listar_status_maquinas(
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "OPERADOR", "MANUTENCAO"])
    ),
):
    """Retorna o estado atualizado de todas as máquinas."""
    dados = await repository.obter_status_atual(conn)
    return [dict(row) for row in dados]


@app.get(
    "/status-maquinas/{maquina_id}",
    response_model=MaquinaStatusResponse,
    tags=["Telemetria IoT"],
)
async def listar_status_por_id(
    maquina_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "OPERADOR", "MANUTENCAO"])
    ),
):
    """Retorna o status de uma única máquina específica."""
    dados = await repository.obter_status_por_id(conn, maquina_id)
    if not dados:
        raise HTTPException(status_code=404, detail="Status da máquina não encontrado.")
    return dict(dados)


# ==========================================
# HISTÓRICO DE LOGS E AUDITORIA
# ==========================================


@app.get(
    "/auditoria",
    response_model=list[AuditLogResponse],
    tags=["Auditoria e Segurança"],
)
async def listar_auditoria(
    usuario_id: int | None = Query(
        None, description="Filtrar por ID de usuário específico"
    ),
    limite: int = Query(
        100, ge=1, le=500, description="Quantidade máxima de registros"
    ),
    conn: asyncpg.Connection = Depends(get_db),
    _: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),  # <- 'usuario_atual' alterado para '_'
):
    """Retorna a trilha de auditoria completa da aplicação (ações executadas por usuários).

    Apenas administradores têm acesso a este relatório em modo SOMENTE LEITURA.
    """
    logs = await repository.listar_logs_auditoria(
        conn, usuario_id=usuario_id, limite=limite
    )
    return logs


@app.get("/logs", response_model=list[LogMaquinaResponse], tags=["Telemetria e Logs"])
async def listar_historico_de_logs(
    maquina_id: int | None = Query(
        None, description="Filtrar por ID de uma máquina específica"
    ),
    periodo: str = Query(
        "hoje", description="Opções válidas: hoje, semana, mes, customizado"
    ),
    data_inicio: date | None = Query(
        None, description="Obrigatório se período for 'customizado' (AAAA-MM-DD)"
    ),
    data_fim: date | None = Query(
        None, description="Obrigatório se período for 'customizado' (AAAA-MM-DD)"
    ),
    limite: int = Query(
        500,
        description="Limite máximo de registros retornados para evitar overhead",
        ge=1,
        le=1000,
    ),
    conn: asyncpg.Connection = Depends(get_db),
    _: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "OPERADOR", "MANUTENCAO"])
    ),  # <- 'usuario_atual' alterado para '_'
):
    """Retorna o histórico de logs das máquinas com opções de filtros por período."""
    if periodo == "customizado" and (not data_inicio or not data_fim):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Para buscas com o período 'customizado', você deve informar as"
                " datas de início e fim."
            ),
        )

    logs = await repository.buscar_historico_logs(
        conn=conn,
        maquina_id=maquina_id,
        periodo=periodo,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=limite,
    )

    return logs


@app.post("/login", tags=["Autenticação"])
async def login(credenciais: LoginRequest, conn: asyncpg.Connection = Depends(get_db)):
    email_normalizado = credenciais.email.lower().strip()
    funcionario = await repository.obter_funcionario_por_email(conn, email_normalizado)

    if not funcionario or not pwd_context.verify(
        credenciais.senha, funcionario["senha_hash"]
    ):
        if funcionario:
            await repository.registrar_auditoria(
                conn=conn,
                usuario_id=funcionario["id"],
                acao="LOGIN_FALHA",
                entidade="funcionarios",
                entidade_id=funcionario["id"],
                detalhes="Tentativa de login com senha incorreta",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Gera JWT contendo ID, e-mail e perfil (Role)
    access_token = auth.criar_token_acesso(
        dados={
            "sub": str(funcionario["id"]),
            "email": funcionario["email"],
            "perfil": funcionario["perfil"],
        }
    )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=funcionario["id"],
        acao="LOGIN_SUCESSO",
        entidade="funcionarios",
        entidade_id=funcionario["id"],
        detalhes=f"Login realizado com sucesso ({funcionario['perfil']})",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": {
            "id": funcionario["id"],
            "nome": funcionario["nome"],
            "email": funcionario["email"],
            "perfil": funcionario["perfil"],
        },
    }


# ==========================================
# CRUD MÁQUINAS
# ==========================================


@app.get("/maquinas", response_model=list[MaquinaResponse], tags=["CRUD Máquinas"])
async def listar_maquinas(
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "OPERADOR", "MANUTENCAO"])
    ),
):
    """Retorna a lista de todas as máquinas ativas."""
    maquinas = await repository.listar_maquinas_cadastradas(conn)
    return maquinas


@app.get(
    "/maquinas/{maquina_id}",
    response_model=MaquinaResponse,
    tags=["CRUD Máquinas"],
)
async def obter_maquina(
    maquina_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "OPERADOR", "MANUTENCAO"])
    ),
):
    """Retorna os detalhes de uma máquina específica."""
    maquina = await repository.obter_maquina_por_id(conn, maquina_id)
    if not maquina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Máquina não encontrada ou já desativada.",
        )
    return maquina


@app.post(
    "/maquinas",
    response_model=MaquinaResponse,
    status_code=201,
    tags=["CRUD Máquinas"],
)
async def post_maquina(
    maquina_dados: MaquinaCreate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Cadastra uma nova máquina na planta industrial."""
    dados_repositorio = maquina_dados.model_dump()

    try:
        nova_maquina = await repository.cadastrar_maquina(conn, dados_repositorio)
        if not nova_maquina:
            raise HTTPException(
                status_code=500, detail="Erro interno ao registrar a máquina."
            )
        return dict(nova_maquina)
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A TAG '{maquina_dados.tag_maquina.upper()}' já está cadastrada em"
                " outra máquina ativa."
            ),
        )


@app.put(
    "/maquinas/{maquina_id}",
    response_model=MaquinaResponse,
    tags=["CRUD Máquinas"],
)
async def atualizar_cadastro_maquina(
    maquina_id: int,
    maquina_dados: MaquinaUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Altera os dados cadastrais de uma máquina."""
    try:
        sucesso = await repository.atualizar_maquina(
            conn, maquina_id, maquina_dados.model_dump()
        )

        if not sucesso:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Máquina não encontrada ou desativada do sistema.",
            )

        return {
            "id": maquina_id,
            "tag_maquina": maquina_dados.tag_maquina.upper().strip(),
            "nome_maquina": maquina_dados.nome_maquina.strip(),
            "setor": maquina_dados.setor,
            "data_cadastro": datetime.now(),
        }
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A Tag '{maquina_dados.tag_maquina.upper()}' já está sendo usada"
                " por outra máquina."
            ),
        )


@app.delete("/maquinas/{maquina_id}", tags=["CRUD Máquinas"])
async def deletar_maquina(
    maquina_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Aplica Soft Delete em uma máquina."""
    sucesso = await repository.soft_delete_maquina(conn, maquina_id)
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Máquina não encontrada ou já removida do sistema.",
        )
    return {
        "status": "Sucesso",
        "mensagem": f"Máquina {maquina_id} desativada logicamente.",
    }


# ==========================================
# CRUD FUNCIONÁRIOS
# ==========================================


@app.get(
    "/funcionarios",
    response_model=list[FuncionarioResponse],
    tags=["CRUD Funcionários"],
)
async def listar_funcionarios(
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Retorna a lista de funcionários ativos."""
    funcionarios = await repository.listar_funcionarios_ativos(conn)
    return funcionarios


@app.post(
    "/funcionarios",
    response_model=FuncionarioResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["CRUD Funcionários"],
)
async def cadastrar_funcionario(
    funcionario: FuncionarioCreate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Cadastra um novo funcionário com senha criptografada e auditoria."""
    dados_repositorio = funcionario.model_dump()
    dados_repositorio["email"] = funcionario.email.lower().strip()

    senha_puro = dados_repositorio.pop("senha")
    dados_repositorio["senha_hash"] = pwd_context.hash(senha_puro)

    try:
        id_gerado = await repository.cadastrar_funcionario(conn, dados_repositorio)

        if not id_gerado:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=("Erro interno ao registrar o funcionário no banco de dados."),
            )

        await repository.registrar_auditoria(
            conn=conn,
            usuario_id=usuario_atual.id,
            acao="CRIAR_FUNCIONARIO",
            entidade="funcionarios",
            entidade_id=id_gerado,
            detalhes=(
                f"Criou o funcionário '{funcionario.nome}'"
                f" ({dados_repositorio['email']}) com perfil"
                f" '{funcionario.perfil}'."
            ),
        )

        return {
            "id": id_gerado,
            "nome": funcionario.nome,
            "cargo": funcionario.cargo,
            "turno_trabalho": funcionario.turno_trabalho,
            "ativo": True,
            "email": dados_repositorio["email"],
            "perfil": funcionario.perfil,
        }

    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um funcionário ATIVO cadastrado com este e-mail.",
        )


@app.get(
    "/funcionarios/{funcionario_id}",
    response_model=FuncionarioResponse,
    tags=["CRUD Funcionários"],
)
async def get_funcionario_por_id(
    funcionario_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Retorna detalhes de um funcionário específico."""
    funcionario = await repository.obter_funcionario_por_id(conn, funcionario_id)
    if not funcionario:
        raise HTTPException(
            status_code=404, detail="Funcionário não encontrado ou inativo."
        )
    return funcionario


@app.put(
    "/funcionarios/{funcionario_id}",
    response_model=FuncionarioResponse,
    tags=["CRUD Funcionários"],
)
async def put_funcionario(
    funcionario_id: int,
    funcionario_dados: FuncionarioUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Atualiza dados cadastrais de um funcionário."""
    dados_repositorio = funcionario_dados.model_dump()

    try:
        sucesso = await repository.atualizar_funcionario(
            conn, funcionario_id, dados_repositorio
        )
        if not sucesso:
            raise HTTPException(
                status_code=404, detail="Funcionário não encontrado ou inativo."
            )

        await repository.registrar_auditoria(
            conn=conn,
            usuario_id=usuario_atual.id,
            acao="ATUALIZAR_FUNCIONARIO",
            entidade="funcionarios",
            entidade_id=funcionario_id,
            detalhes=(
                f"Atualizou o cadastro do funcionário '{funcionario_dados.nome}'"
                f" (Perfil: '{funcionario_dados.perfil}')."
            ),
        )

        return {
            "id": funcionario_id,
            "nome": funcionario_dados.nome,
            "cargo": funcionario_dados.cargo,
            "turno_trabalho": funcionario_dados.turno_trabalho,
            "email": funcionario_dados.email,
            "ativo": funcionario_dados.ativo,
            "perfil": funcionario_dados.perfil,
        }
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=400,
            detail="O e-mail informado já está em uso por outro usuário ativo.",
        )


@app.delete("/funcionarios/{funcionario_id}", tags=["CRUD Funcionários"])
async def deletar_funcionario(
    funcionario_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(auth.PermissaoRequerida(["ADMIN"])),
):
    """Aplica Soft Delete em um funcionário."""
    sucesso = await repository.soft_delete_funcionario(conn, funcionario_id)
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funcionário não encontrado ou já deletado.",
        )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="DESATIVAR_FUNCIONARIO",
        entidade="funcionarios",
        entidade_id=funcionario_id,
        detalhes=f"Desativou (soft delete) o funcionário ID {funcionario_id}.",
    )

    return {
        "status": "Sucesso",
        "mensagem": f"Funcionário {funcionario_id} desativado logicamente.",
    }


# ==========================================
# PLANO DE MANUTENÇÃO (PREVENTIVA / PREDITIVA)
# ==========================================


@app.post(
    "/manutencoes",
    response_model=ManutencaoPreventivaResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Plano de Manutenção"],
)
async def agendar_nova_manutencao(
    manutencao: ManutencaoPreventivaCreate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Agenda uma nova ordem de manutenção."""
    nova_manutencao = await repository.agendar_manutencao(conn, manutencao.model_dump())

    if not nova_manutencao:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Erro ao agendar manutenção. Verifique se a máquina informada"
                " existe e está ativa."
            ),
        )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="AGENDAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=nova_manutencao["id"],
        detalhes=(
            f"Agendou manutenção '{nova_manutencao['tipo_manutencao']}' para a"
            f" Máquina ID {nova_manutencao['maquina_id']}."
        ),
    )

    return nova_manutencao


@app.get(
    "/manutencoes",
    response_model=list[ManutencaoPreventivaDetalhadaResponse],
    tags=["Plano de Manutenção"],
)
async def listar_todas_manutencoes(
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Retorna a lista completa de manutenções detalhadas."""
    return await repository.listar_manutencoes_detalhadas(conn)


@app.get(
    "/manutencoes/{manutencao_id}",
    response_model=ManutencaoPreventivaDetalhadaResponse,
    tags=["Plano de Manutenção"],
)
async def obter_manutencao_por_id(
    manutencao_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Busca os detalhes de uma ordem de manutenção pelo ID."""
    manutencao = await repository.obter_manutencao_por_id(conn, manutencao_id)
    if not manutencao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de manutenção não encontrada.",
        )
    return manutencao


@app.put(
    "/manutencoes/{manutencao_id}",
    response_model=ManutencaoPreventivaDetalhadaResponse,
    tags=["Plano de Manutenção"],
)
async def atualizar_dados_manutencao(
    manutencao_id: int,
    dados_novos: ManutencaoPreventivaUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Atualiza informações de uma ordem de manutenção aberta."""
    sucesso = await repository.atualizar_dados_manutencao(
        conn, manutencao_id, dados_novos.model_dump()
    )
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Não foi possível atualizar. A ordem pode não existir ou já está"
                " CONCLUÍDA."
            ),
        )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="ATUALIZAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=manutencao_id,
        detalhes=(
            f"Atualizou dados/agendamento da ordem de manutenção ID {manutencao_id}."
        ),
    )

    registro_atualizado = await repository.obter_manutencao_por_id(conn, manutencao_id)
    return registro_atualizado


@app.patch(
    "/manutencoes/{manutencao_id}/concluir",
    response_model=ManutencaoPreventivaDetalhadaResponse,
    tags=["Plano de Manutenção"],
)
async def concluir_ordem_manutencao(
    manutencao_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Encerra a ordem de manutenção vinculando ao técnico logado no JWT."""
    sucesso = await repository.concluir_ordem_manutencao(
        conn, manutencao_id, usuario_atual.id
    )
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Falha ao encerrar ordem. Verifique se a ordem existe ou se já foi"
                " fechada."
            ),
        )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="CONCLUIR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=manutencao_id,
        detalhes=f"Concluiu a ordem de manutenção ID {manutencao_id}.",
    )

    registro_atualizado = await repository.obter_manutencao_por_id(conn, manutencao_id)
    return registro_atualizado


@app.delete("/manutencoes/{manutencao_id}", tags=["Plano de Manutenção"])
async def deletar_manutencao_logica(
    manutencao_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """Aplica Soft Delete em uma manutenção aberta."""
    sucesso = await repository.soft_delete_manutencao(conn, manutencao_id)
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Não é possível remover. A ordem pode não existir, já foi"
                " concluída ou já foi excluída."
            ),
        )

    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="DELETAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=manutencao_id,
        detalhes=(
            "Cancelou/desativou (soft delete) a ordem de manutenção ID"
            f" {manutencao_id}."
        ),
    )

    return {
        "status": "Sucesso",
        "mensagem": f"Ordem {manutencao_id} desativada logicamente.",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
