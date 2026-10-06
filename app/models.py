from enum import Enum
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime, date
from typing import Literal

# ==========================================
# CONFIGURAÇÃO BASE DO MODELO Pydantic / ORM
# ==========================================


class ResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StatusMaquina(str, Enum):
    ativa = "Ativa"
    inativa = "Inativa"
    desligada = "Desligada"
    manutencao = "Manutenção"


# ==========================================
# TELEMETRIA E LEITURA DE SENSORES (ESP32 / SIMULADOR)
# ==========================================


class LeituraSensor(BaseModel):
    maquina_id: int = Field(gt=0, description="O ID deve ser maior que 0")
    vibracao_rms: float = Field(ge=0.0, description="Vibração não pode ser negativa")
    corrente_ampere: float = Field(ge=0.0, description="Corrente não pode ser negativa")
    tensao_volt: float = Field(
        ge=0.0, le=250.0, description="Tensão deve estar entre 0 e 250V"
    )
    potencia_watt: float = Field(ge=0.0, description="Potência não pode ser negativa")
    frequencia_hz: float = Field(
        ge=0.0, le=100.0, description="Frequência industrial padrão entre 0 e 100Hz"
    )
    status_atual: StatusMaquina


class MaquinaStatusResponse(ResponseBase):
    maquina_id: int
    tag_maquina: str
    nome_maquina: str
    status_atual: StatusMaquina
    vibracao_rms: float
    corrente_ampere: float
    tensao_volt: float
    potencia_watt: float
    frequencia_hz: float
    momento_da_leitura: datetime


class LogMaquinaResponse(ResponseBase):
    id: int
    horario_do_log: datetime
    maquina_id: int
    turno: int | None = Field(
        None, description="Turno em que o dado foi gerado (1, 2 ou 3)"
    )
    vibracao_rms: float
    corrente_ampere: float
    tensao_volt: float
    potencia_watt: float
    status_no_momento: StatusMaquina
    frequencia_hz: float


# ==========================================
# GESTÃO DE USUÁRIOS E FUNCIONÁRIOS
# ==========================================


class FuncionarioCreate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=100, description="Nome completo")
    cargo: str = Field(..., min_length=2, max_length=50, description="Cargo ou função")
    turno_trabalho: int = Field(
        ..., ge=1, le=3, description="Turno de trabalho (1, 2 ou 3)"
    )
    email: EmailStr = Field(..., description="E-mail corporativo que será o login")
    senha: str = Field(
        ..., min_length=6, description="Senha em texto puro para criptografia"
    )
    perfil: Literal["ADMIN", "OPERADOR", "MANUTENCAO"] = Field(
        "OPERADOR", description="Perfil de acesso"
    )


class FuncionarioResponse(ResponseBase):
    id: int
    nome: str
    cargo: str
    turno_trabalho: int
    ativo: bool
    email: str
    perfil: str


class FuncionarioUpdate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=100, description="Nome completo")
    cargo: str = Field(..., min_length=2, max_length=50, description="Cargo ou função")
    turno_trabalho: int = Field(
        ..., ge=1, le=3, description="Turno de trabalho (1, 2 ou 3)"
    )
    email: EmailStr = Field(..., description="E-mail corporativo")
    ativo: bool = Field(True, description="Status do funcionário no sistema")
    perfil: Literal["ADMIN", "OPERADOR", "MANUTENCAO"] = Field(
        "OPERADOR", description="Perfil de acesso do funcionário"
    )


# ==========================================
# CADASTRO E GERENCIAMENTO DE MÁQUINAS (CRUD)
# ==========================================


class MaquinaCreate(BaseModel):
    tag_maquina: str = Field(
        ..., min_length=2, max_length=20, description="Ex: INJ-01, MTR-03"
    )
    nome_maquina: str = Field(
        ..., min_length=3, max_length=100, description="Ex: Injetora Hidráulica 500T"
    )
    setor: str | None = Field(
        None, max_length=50, description="Ex: Estamparia, Utilidades"
    )


class MaquinaUpdate(BaseModel):
    tag_maquina: str = Field(..., min_length=2, max_length=20)
    nome_maquina: str = Field(..., min_length=3, max_length=100)
    setor: str | None = Field(None, max_length=50)


class MaquinaResponse(ResponseBase):
    id: int
    tag_maquina: str
    nome_maquina: str
    setor: str | None
    data_cadastro: datetime


# ==========================================
# MANUTENÇÃO PREVENTIVA E PREDITIVA
# ==========================================


class ManutencaoPreventivaCreate(BaseModel):
    maquina_id: int = Field(..., description="ID da máquina que sofrerá a intervenção")
    descricao_servico: str = Field(
        ..., min_length=5, description="Detalhes do plano de manutenção"
    )
    data_agendada: date = Field(
        ..., description="Data programada para a execução (AAAA-MM-DD)"
    )
    tipo_manutencao: Literal["Preventiva", "Preditiva"] = Field(
        "Preventiva", description="Tipo restrito pelo banco"
    )


class ManutencaoPreventivaUpdate(BaseModel):
    descricao_servico: str = Field(..., min_length=5)
    data_agendada: date
    tipo_manutencao: Literal["Preventiva", "Preditiva"]


class ManutencaoPreventivaConcluir(BaseModel):
    funcionario_id: int = Field(..., description="ID do técnico que realizou o serviço")


class ManutencaoPreventivaResponse(ResponseBase):
    id: int
    maquina_id: int | None
    descricao_servico: str | None
    data_agendada: date
    concluida: bool
    data_conclusao_real: datetime | None
    funcionario_id: int | None
    tipo_manutencao: str


class ManutencaoPreventivaDetalhadaResponse(ResponseBase):
    id: int
    maquina_id: int | None
    tag_maquina: str | None
    nome_maquina: str | None
    descricao_servico: str | None
    data_agendada: date
    concluida: bool
    data_conclusao_real: datetime | None
    funcionario_id: int | None
    nome_funcionario: str | None
    tipo_manutencao: str
