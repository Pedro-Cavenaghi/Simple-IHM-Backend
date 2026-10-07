from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel
from datetime import datetime, date
import os
import asyncpg
import warnings
from passlib.context import CryptContext

from .database import Database, get_db
import app.repository as repository
from app import auth

# Importações internas
from .models import (
    LeituraSensor,
    MaquinaStatusResponse,
    MaquinaCreate,
    MaquinaResponse,
    MaquinaUpdate,
    FuncionarioCreate,
    FuncionarioResponse,
    FuncionarioUpdate,
    ManutencaoPreventivaCreate,
    ManutencaoPreventivaUpdate,
    ManutencaoPreventivaResponse,
    ManutencaoPreventivaDetalhadaResponse,
    LogMaquinaResponse,
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


# --- ENDPOINTS DE TELEMETRIA (IOT) ---


@app.get(
    "/status-maquinas",
    response_model=list[MaquinaStatusResponse],
    tags=["Telemetria IoT"],
)
async def listar_status_maquinas(conn: asyncpg.Connection = Depends(get_db)):
    """
    Retorna o estado atual de todas as máquinas para os cards em tempo real do React.
    """
    dados = await repository.obter_status_atual(conn)
    return [dict(row) for row in dados]


@app.get(
    "/status-maquinas/{maquina_id}",
    response_model=MaquinaStatusResponse,
    tags=["Telemetria IoT"],
)
async def listar_status_por_id(
    maquina_id: int, conn: asyncpg.Connection = Depends(get_db)
):
    """
    Retorna o status de uma única máquina específica.
    """
    dados = await repository.obter_status_por_id(conn, maquina_id)
    if not dados:
        raise HTTPException(status_code=404, detail="Status da máquina não encontrado.")
    return dict(dados)


@app.post("/enviar-dados", status_code=status.HTTP_200_OK, tags=["Telemetria IoT"])
async def receber_dados(
    leitura: LeituraSensor, conn: asyncpg.Connection = Depends(get_db)
):
    """
    Endpoint consumido pela ESP32 / Simulador para registrar logs históricos
    e atualizar o painel em tempo real (UPSERT).
    """
    sucesso = await repository.salvar_leitura(conn, leitura.model_dump())
    if sucesso:
        return {"status": "Sucesso", "mensagem": "Dados gravados"}
    else:
        raise HTTPException(
            status_code=500, detail="Erro ao gravar os dados de telemetria no banco"
        )


# --- ENDPOINT DE TELEMETRIA E HISTÓRICO DE LOGS (DASHBOARD) ---


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
    ),  # <-- Adicionado com validação (mínimo 1, máximo 1000)
    conn: asyncpg.Connection = Depends(get_db),
):
    """
    Retorna a lista de telemetria histórica/logs das máquinas da planta industrial.
    Permite filtros rápidos por períodos (hoje, semana, mês) ou intervalos customizados.
    """

    if periodo == "customizado" and (not data_inicio or not data_fim):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para buscas com o período 'customizado', você deve informar as datas de início e fim.",
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
        # Auditoria de tentativa falha
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

    # Gera JWT
    access_token = auth.criar_token_acesso(
        dados={
            "sub": str(funcionario["id"]),
            "email": funcionario["email"],
            "perfil": funcionario["perfil"],
        }
    )

    # Auditoria de login bem-sucedido
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


# --- CRUD MAQUINAS ---


@app.get("/maquinas", response_model=list[MaquinaResponse], tags=["CRUD Máquinas"])
async def listar_maquinas(conn: asyncpg.Connection = Depends(get_db)):
    """
    Retorna a lista de todas as máquinas ativas (sem Soft Delete).
    """
    maquinas = await repository.listar_maquinas_cadastradas(conn)
    return maquinas


@app.get(
    "/maquinas/{maquina_id}", response_model=MaquinaResponse, tags=["CRUD Máquinas"]
)
async def obter_maquina(maquina_id: int, conn: asyncpg.Connection = Depends(get_db)):
    """
    Retorna os detalhes de uma máquina específica pelo ID.
    """
    maquina = await repository.obter_maquina_por_id(conn, maquina_id)
    if not maquina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Máquina não encontrada ou já desativada.",
        )
    return maquina


@app.post(
    "/maquinas", response_model=MaquinaResponse, status_code=201, tags=["CRUD Máquinas"]
)
async def post_maquina(
    maquina_dados: MaquinaCreate, conn: asyncpg.Connection = Depends(get_db)
):
    """
    Cadastra uma nova máquina no ecossistema industrial.
    """
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
            detail=f"A TAG '{maquina_dados.tag_maquina.upper()}' já está cadastrada em outra máquina ativa.",
        )


@app.delete("/maquinas/{maquina_id}", tags=["CRUD Máquinas"])
async def deletar_maquina(maquina_id: int, conn: asyncpg.Connection = Depends(get_db)):
    """
    Aplica exclusão lógica em uma máquina, preservando logs e histórico.
    """
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


@app.put(
    "/maquinas/{maquina_id}", response_model=MaquinaResponse, tags=["CRUD Máquinas"]
)
async def atualizar_cadastro_maquina(
    maquina_id: int,
    maquina_dados: MaquinaUpdate,
    conn: asyncpg.Connection = Depends(get_db),
):
    """
    Altera os dados cadastrais de uma máquina.
    """
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
            detail=f"A Tag '{maquina_dados.tag_maquina.upper()}' já está sendo usada por outra máquina.",
        )


# ==========================================
# ENDPOINTS DO CRUD DO DASHBOARD (FUNCIONÁRIOS)
# ==========================================


@app.get(
    "/funcionarios",
    response_model=list[FuncionarioResponse],
    tags=["CRUD Funcionários"],
)
async def listar_funcionarios(
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),
):
    """
    Retorna a lista de funcionários ativos (que não sofreram soft delete) para a tabela do Dashboard.
    """
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
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),
):
    """
    Cadastra um novo funcionário com e-mail normalizado (minúsculas/sem espaços)
    e hash de senha seguro. Registra o evento no audit_logs vinculando ao ADMIN executante.
    """
    dados_repositorio = funcionario.model_dump()

    # Normalização de dados
    dados_repositorio["email"] = funcionario.email.lower().strip()

    senha_puro = dados_repositorio.pop("senha")
    dados_repositorio["senha_hash"] = pwd_context.hash(senha_puro)

    try:
        id_gerado = await repository.cadastrar_funcionario(conn, dados_repositorio)

        if not id_gerado:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao registrar o funcionário no banco de dados.",
            )

        # 📝 AUDITORIA: Registra a criação do novo funcionário
        await repository.registrar_auditoria(
            conn=conn,
            usuario_id=usuario_atual.id,
            acao="CRIAR_FUNCIONARIO",
            entidade="funcionarios",
            entidade_id=id_gerado,
            detalhes=f"Criou o funcionário '{funcionario.nome}' ({dados_repositorio['email']}) com perfil '{funcionario.perfil}'.",
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
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),
):
    """
    Retorna os detalhes de um funcionário específico pelo ID.
    """
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
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),
):
    """
    Atualiza os dados cadastrais administrativos de um funcionário.
    A alteração de senha é bloqueada e isolada deste fluxo.
    """
    dados_repositorio = funcionario_dados.model_dump()

    try:
        sucesso = await repository.atualizar_funcionario(
            conn, funcionario_id, dados_repositorio
        )
        if not sucesso:
            raise HTTPException(
                status_code=404, detail="Funcionário não encontrado ou inativo."
            )

        # 📝 AUDITORIA: Registra a alteração dos dados cadastrais
        await repository.registrar_auditoria(
            conn=conn,
            usuario_id=usuario_atual.id,
            acao="ATUALIZAR_FUNCIONARIO",
            entidade="funcionarios",
            entidade_id=funcionario_id,
            detalhes=f"Atualizou o cadastro do funcionário '{funcionario_dados.nome}' (Perfil: '{funcionario_dados.perfil}').",
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


@app.delete(
    "/funcionarios/{funcionario_id}",
    tags=["CRUD Funcionários"],
)
async def deletar_funcionario(
    funcionario_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN"])
    ),
):
    """
    Aplica Soft Delete em um funcionário do sistema. O registro permanece no banco para auditoria.
    """
    sucesso = await repository.soft_delete_funcionario(conn, funcionario_id)
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funcionário não encontrado ou já deletado.",
        )

    # 📝 AUDITORIA: Registra a desativação (soft delete)
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
# ENDPOINTS DO PLANO DE MANUTENÇÃO (PREVENTIVA / PREDITIVA)
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
    """
    Agenda uma nova intervenção (Preventiva ou Preditiva) para uma máquina da planta.
    A ordem nasce com o status 'concluida = false'.
    """
    nova_manutencao = await repository.agendar_manutencao(conn, manutencao.model_dump())
    
    if not nova_manutencao:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erro ao agendar manutenção. Verifique se a máquina informada existe e está ativa.",
        )

    # 📝 AUDITORIA: Registra o agendamento vinculando ao usuário logado
    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="AGENDAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=nova_manutencao["id"],
        detalhes=f"Agendou manutenção '{nova_manutencao['tipo_manutencao']}' para a Máquina ID {nova_manutencao['maquina_id']}.",
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
    """
    Retorna a lista completa de manutenções trazendo as tags/nomes das máquinas
    e os nomes dos técnicos via LEFT JOIN (ideal para a tabela do Dashboard).
    """
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
    """
    Busca os detalhes completos de uma ordem de manutenção específica pelo ID.
    """
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
    """
    Modifica a descrição, data ou tipo de uma manutenção, desde que ela ainda esteja ABERTA.
    Retorna os dados ricos atualizados para sincronia do estado no React.
    """
    sucesso = await repository.atualizar_dados_manutencao(
        conn, manutencao_id, dados_novos.model_dump()
    )
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível atualizar. A ordem pode não existir ou já está CONCLUÍDA.",
        )

    # 📝 AUDITORIA: Registra a atualização do agendamento
    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="ATUALIZAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=manutencao_id,
        detalhes=f"Atualizou dados/agendamento da ordem de manutenção ID {manutencao_id}.",
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
    """
    Dá baixa/encerra a ordem de manutenção. O banco registrará o timestamp exato do NOW()
    e atribuirá o técnico logado no JWT.
    """
    # Usa o ID do usuário autenticado no JWT para dar baixa na ordem
    sucesso = await repository.concluir_ordem_manutencao(
        conn, manutencao_id, usuario_atual.id
    )
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falha ao encerrar ordem. Verifique se a ordem existe ou se já foi fechada.",
        )

    # 📝 AUDITORIA: Registra o encerramento da manutenção
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


@app.delete(
    "/manutencoes/{manutencao_id}",
    tags=["Plano de Manutenção"],
)
async def deletar_manutencao_logica(
    manutencao_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    usuario_atual: FuncionarioResponse = Depends(
        auth.PermissaoRequerida(["ADMIN", "MANUTENCAO"])
    ),
):
    """
    Aplica exclusão lógica (Soft Delete) em um agendamento, desde que a ordem esteja aberta.
    """
    sucesso = await repository.soft_delete_manutencao(conn, manutencao_id)
    if not sucesso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível remover. A ordem pode não existir, já foi concluída ou já foi excluída.",
        )

    # 📝 AUDITORIA: Registra a remoção lógica
    await repository.registrar_auditoria(
        conn=conn,
        usuario_id=usuario_atual.id,
        acao="DELETAR_MANUTENCAO",
        entidade="manutencao_preventiva",
        entidade_id=manutencao_id,
        detalhes=f"Cancelou/desativou (soft delete) a ordem de manutenção ID {manutencao_id}.",
    )

    return {
        "status": "Sucesso",
        "mensagem": f"Ordem {manutencao_id} desativada logicamente.",
    }