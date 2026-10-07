import asyncpg
from datetime import datetime, date, time


# ==========================================
# UTILITÁRIOS DA OPERAÇÃO INDUSTRIAL
# ==========================================


def descobrir_turno_atual() -> int:
    hora_atual = datetime.now().time()

    if time(6, 0) <= hora_atual < time(14, 0):
        return 1
    elif time(14, 0) <= hora_atual < time(22, 0):
        return 2
    else:
        return 3


# ==========================================
# LOGS DE AUDITORIA
# ==========================================


async def registrar_auditoria(
    conn: asyncpg.Connection,
    usuario_id: int | None,
    acao: str,
    entidade: str,
    entidade_id: int | None = None,
    detalhes: str | None = None,
) -> bool:
    """
    Grava um evento de auditoria no banco de dados.
    """
    sql = """
        INSERT INTO audit_logs (usuario_id, acao, entidade, entidade_id, detalhes)
        VALUES ($1, $2, $3, $4, $5);
    """
    try:
        await conn.execute(sql, usuario_id, acao, entidade, entidade_id, detalhes)
        return True
    except Exception as e:
        print(f"Erro ao registrar auditoria no Repository: {e}")
        return False


# ==========================================
# TELEMETRIA E HISTÓRICO DOS SENSORES (IoT)
# ==========================================


async def salvar_leitura(conn: asyncpg.Connection, dados: dict) -> bool:
    try:
        turno_atual = descobrir_turno_atual()

        async with conn.transaction():
            query_log = """
                INSERT INTO logs_maquinas 
                (maquina_id, status_no_momento, vibracao_rms, corrente_ampere, tensao_volt, potencia_watt, turno, frequencia_hz) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
            """
            await conn.execute(
                query_log,
                dados["maquina_id"],
                dados["status_atual"],
                dados["vibracao_rms"],
                dados["corrente_ampere"],
                dados["tensao_volt"],
                dados["potencia_watt"],
                turno_atual,
                dados.get("frequencia_hz", 0.0),
            )

            query_upsert = """
                INSERT INTO status_atual_maquinas 
                (maquina_id, status_atual, vibracao_rms, corrente_ampere, tensao_volt, potencia_watt, frequencia_hz, momento_da_leitura)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                ON CONFLICT (maquina_id) 
                DO UPDATE SET 
                    status_atual = EXCLUDED.status_atual, 
                    vibracao_rms = EXCLUDED.vibracao_rms, 
                    corrente_ampere = EXCLUDED.corrente_ampere, 
                    tensao_volt = EXCLUDED.tensao_volt, 
                    potencia_watt = EXCLUDED.potencia_watt, 
                    frequencia_hz = EXCLUDED.frequencia_hz,
                    momento_da_leitura = NOW();
            """
            await conn.execute(
                query_upsert,
                dados["maquina_id"],
                dados["status_atual"],
                dados["vibracao_rms"],
                dados["corrente_ampere"],
                dados["tensao_volt"],
                dados["potencia_watt"],
                dados.get("frequencia_hz", 0.0),
            )

        return True
    except Exception as e:
        print(f"Erro no SQL ao salvar: {e}")
        return False


async def obter_status_atual(conn: asyncpg.Connection):
    try:
        sql = """
            SELECT 
                s.maquina_id,
                m.tag_maquina,
                m.nome_maquina,
                s.status_atual, 
                s.vibracao_rms, 
                s.corrente_ampere, 
                s.tensao_volt, 
                s.potencia_watt, 
                s.frequencia_hz,
                s.momento_da_leitura 
            FROM status_atual_maquinas s
            INNER JOIN maquinas m ON s.maquina_id = m.id
            WHERE m.deletado_em IS NULL
            ORDER BY m.tag_maquina ASC;
        """
        return await conn.fetch(sql)
    except Exception as e:
        print(f"Erro ao buscar status das máquinas com informações cadastrais: {e}")
        return []


async def obter_status_por_id(conn: asyncpg.Connection, maquina_id: int) -> dict | None:
    try:
        sql = """
            SELECT 
                s.maquina_id,
                m.tag_maquina,
                m.nome_maquina,
                s.status_atual, 
                s.vibracao_rms, 
                s.corrente_ampere, 
                s.tensao_volt, 
                s.potencia_watt, 
                s.frequencia_hz,
                s.momento_da_leitura 
            FROM status_atual_maquinas s
            INNER JOIN maquinas m ON s.maquina_id = m.id
            WHERE s.maquina_id = $1 AND m.deletado_em IS NULL;
        """
        registro = await conn.fetchrow(sql, maquina_id)

        return dict(registro) if registro else None

    except Exception as e:
        print(f"Erro ao obter status da máquina por ID no Repository: {e}")
        return None


async def buscar_historico_logs(
    conn: asyncpg.Connection,
    maquina_id: int | None,
    periodo: str,
    data_inicio: date | None,
    data_fim: date | None,
    limite: int = 500,
):
    try:
        sql = """
            SELECT 
                id, 
                horario_do_log, 
                maquina_id, 
                turno, 
                vibracao_rms, 
                corrente_ampere, 
                tensao_volt, 
                potencia_watt, 
                status_no_momento, 
                frequencia_hz
            FROM logs_maquinas
            WHERE 1=1
        """

        parametros = []
        contador = 1

        if maquina_id is not None:
            sql += f" AND maquina_id = ${contador}"
            parametros.append(maquina_id)
            contador += 1

        if periodo == "hoje":
            sql += " AND horario_do_log >= CURRENT_DATE::timestamp"
        elif periodo == "semana":
            sql += (
                " AND horario_do_log >= (CURRENT_DATE - INTERVAL '7 days')::timestamp"
            )
        elif periodo == "mes":
            sql += (
                " AND horario_do_log >= (CURRENT_DATE - INTERVAL '30 days')::timestamp"
            )
        elif periodo == "customizado" and data_inicio and data_fim:
            sql += f" AND horario_do_log >= ${contador}::timestamp AND horario_do_log < (${contador + 1}::date + 1)::timestamp"
            parametros.append(data_inicio)
            parametros.append(data_fim)
            contador += 2

        sql += " ORDER BY horario_do_log DESC"

        sql += f" LIMIT {limite};"

        registros = await conn.fetch(sql, *parametros)
        return [dict(r) for r in registros]

    except Exception as e:
        print(f"Erro ao buscar histórico de logs no Repository: {e}")
        return []


# ==========================================
# GESTÃO DE RECURSOS HUMANOS (FUNCIONÁRIOS)
# ==========================================


async def cadastrar_funcionario(conn: asyncpg.Connection, dados: dict) -> int | None:
    try:
        sql = """
            INSERT INTO funcionarios (nome, cargo, turno_trabalho, email, senha_hash, ativo, perfil)
            VALUES ($1, $2, $3, LOWER($4), $5, $6, $7)
            RETURNING id;
        """
        id_gerado = await conn.fetchval(
            sql,
            dados["nome"],
            dados["cargo"],
            dados["turno_trabalho"],
            dados["email"],
            dados["senha_hash"],
            dados.get("ativo", True),
            dados.get("perfil", "OPERADOR"),
        )
        return id_gerado
    except asyncpg.exceptions.UniqueViolationError:
        # Relança para tratamento de HTTP 400 no FastAPI
        raise
    except Exception as e:
        print(f"Erro ao cadastrar funcionário: {e}")
        return None


async def listar_funcionarios_ativos(conn: asyncpg.Connection):
    try:
        sql = """
            SELECT id, nome, cargo, turno_trabalho, ativo, email, perfil
            FROM funcionarios
            WHERE deletado_em IS NULL
            ORDER BY nome ASC;
        """
        registros = await conn.fetch(sql)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar funcionários: {e}")
        return []


async def soft_delete_funcionario(
    conn: asyncpg.Connection, funcionario_id: int
) -> bool:
    try:
        sql = """
            UPDATE funcionarios
            SET deletado_em = NOW(), ativo = false
            WHERE id = $1 AND deletado_em IS NULL;
        """
        status = await conn.execute(sql, funcionario_id)
        return status == "UPDATE 1"
    except Exception as e:
        print(f"Erro ao aplicar soft delete no funcionário: {e}")
        return False


async def obter_funcionario_por_id(
    conn: asyncpg.Connection, funcionario_id: int
) -> dict | None:
    try:
        sql = """
            SELECT id, nome, cargo, turno_trabalho, ativo, email, perfil
            FROM funcionarios
            WHERE id = $1 AND deletado_em IS NULL;
        """
        registro = await conn.fetchrow(sql, funcionario_id)
        return dict(registro) if registro else None
    except Exception as e:
        print(f"Erro ao obter funcionário por ID: {e}")
        return None


async def atualizar_funcionario(
    conn: asyncpg.Connection, funcionario_id: int, dados: dict
) -> bool:
    try:
        # Atualização explícita incluindo 'perfil', 'LOWER(email)' e registro de alteração
        sql = """
            UPDATE funcionarios
            SET nome = $1,
                cargo = $2,
                turno_trabalho = $3,
                email = LOWER($4),
                perfil = $5,
                ativo = $6,
                ultima_atualizacao = NOW()
            WHERE id = $7 AND deletado_em IS NULL;
        """
        status = await conn.execute(
            sql,
            dados["nome"],
            dados["cargo"],
            dados["turno_trabalho"],
            dados["email"],
            dados.get("perfil", "OPERADOR"),
            dados.get("ativo", True),
            funcionario_id,
        )
        return status == "UPDATE 1"
    except asyncpg.exceptions.UniqueViolationError:
        raise
    except Exception as e:
        print(f"Erro ao atualizar funcionário no Repository: {e}")
        return False


async def obter_funcionario_por_email(
    conn: asyncpg.Connection, email: str
) -> dict | None:
    # 'perfil' adicionado ao SELECT para montagem do Payload do JWT
    sql = """
        SELECT id, nome, email, senha_hash, perfil, ativo 
        FROM funcionarios 
        WHERE LOWER(email) = LOWER($1) AND deletado_em IS NULL;
    """
    registro = await conn.fetchrow(sql, email)
    return dict(registro) if registro else None


# ==========================================
# GERENCIAMENTO CADASTRAL DE MÁQUINAS
# ==========================================


async def cadastrar_maquina(
    conn: asyncpg.Connection, dados: dict
) -> asyncpg.Record | None:
    try:
        sql = """
            INSERT INTO maquinas (tag_maquina, nome_maquina, setor)
            VALUES ($1, $2, $3)
            RETURNING id, tag_maquina, nome_maquina, setor, data_cadastro;
        """
        registro_gerado = await conn.fetchrow(
            sql,
            dados["tag_maquina"].upper().strip(),
            dados["nome_maquina"].strip(),
            dados.get("setor"),
        )
        return registro_gerado
    except asyncpg.UniqueViolationError:
        raise
    except Exception as e:
        print(f"Erro ao cadastrar máquina no Repository: {e}")
        return None


async def listar_maquinas_cadastradas(conn: asyncpg.Connection):
    try:
        sql = """
            SELECT id, tag_maquina, nome_maquina, setor, data_cadastro
            FROM maquinas
            WHERE deletado_em IS NULL
            ORDER BY tag_maquina ASC;
        """
        registros = await conn.fetch(sql)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar máquinas no Repository: {e}")
        return []


async def obter_maquina_por_id(
    conn: asyncpg.Connection, maquina_id: int
) -> dict | None:
    try:
        sql = """
            SELECT id, tag_maquina, nome_maquina, setor, data_cadastro
            FROM maquinas
            WHERE id = $1 AND deletado_em IS NULL;
        """
        registro = await conn.fetchrow(sql, maquina_id)
        return dict(registro) if registro else None
    except Exception as e:
        print(f"Erro ao obter máquina por ID no Repository: {e}")
        return None


async def atualizar_maquina(
    conn: asyncpg.Connection, maquina_id: int, dados: dict
) -> bool:
    try:
        sql = """
            UPDATE maquinas
            SET tag_maquina = $1,
                nome_maquina = $2,
                setor = $3,
                ultima_atualizacao = NOW()
            WHERE id = $4 AND deletado_em IS NULL;
        """
        status = await conn.execute(
            sql,
            dados["tag_maquina"].upper().strip(),
            dados["nome_maquina"].strip(),
            dados.get("setor"),
            maquina_id,
        )
        return status == "UPDATE 1"
    except asyncpg.UniqueViolationError:
        raise
    except Exception as e:
        print(f"Erro ao atualizar máquina no Repository: {e}")
        return False


async def soft_delete_maquina(conn: asyncpg.Connection, maquina_id: int) -> bool:
    try:
        sql = """
            UPDATE maquinas
            SET deletado_em = NOW()
            WHERE id = $1 AND deletado_em IS NULL;
        """
        status = await conn.execute(sql, maquina_id)
        return status == "UPDATE 1"
    except Exception as e:
        print(f"Erro ao aplicar soft delete na máquina: {e}")
        return False


# ==========================================
# MANUTENÇÃO (PREVENTIVA / PREDITIVA)
# ==========================================


async def agendar_manutencao(conn: asyncpg.Connection, dados: dict) -> int | None:
    try:
        sql = """
            INSERT INTO manutencao_preventiva (maquina_id, descricao_servico, data_agendada, tipo_manutencao)
            VALUES ($1, $2, $3, $4)
            RETURNING id;
        """
        id_gerado = await conn.fetchval(
            sql,
            dados["maquina_id"],
            dados["descricao_servico"].strip(),
            dados["data_agendada"],
            dados["tipo_manutencao"],
        )
        return id_gerado
    except Exception as e:
        print(f"Erro ao agendar manutenção no Repository: {e}")
        return None


async def listar_manutencoes_detalhadas(conn: asyncpg.Connection):
    try:
        sql = """
            SELECT 
                mp.id,
                mp.maquina_id,
                m.tag_maquina,
                m.nome_maquina,
                mp.descricao_servico,
                mp.data_agendada,
                mp.concluida,
                mp.data_conclusao_real,
                mp.funcionario_id,
                f.nome as nome_funcionario,
                mp.tipo_manutencao
            FROM manutencao_preventiva mp
            LEFT JOIN maquinas m ON mp.maquina_id = m.id
            LEFT JOIN funcionarios f ON mp.funcionario_id = f.id
            WHERE mp.deletado_em IS NULL
            ORDER BY mp.concluida ASC, mp.data_agendada ASC;
        """
        registros = await conn.fetch(sql)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar manutenções detalhadas: {e}")
        return []


async def obter_manutencao_por_id(
    conn: asyncpg.Connection, manutencao_id: int
) -> dict | None:
    try:
        sql = """
            SELECT 
                mp.id, mp.maquina_id, m.tag_maquina, m.nome_maquina,
                mp.descricao_servico, mp.data_agendada, mp.concluida,
                mp.data_conclusao_real, mp.funcionario_id, f.nome as nome_funcionario,
                mp.tipo_manutencao
            FROM manutencao_preventiva mp
            LEFT JOIN maquinas m ON mp.maquina_id = m.id
            LEFT JOIN funcionarios f ON mp.funcionario_id = f.id
            WHERE mp.id = $1 AND mp.deletado_em IS NULL;
        """
        registro = await conn.fetchrow(sql, manutencao_id)
        return dict(registro) if registro else None
    except Exception as e:
        print(f"Erro ao obter manutenção por ID: {e}")
        return None


async def atualizar_dados_manutencao(
    conn: asyncpg.Connection, manutencao_id: int, dados: dict
) -> bool:
    try:
        sql = """
            UPDATE manutencao_preventiva
            SET descricao_servico = $1,
                data_agendada = $2,
                tipo_manutencao = $3
            WHERE id = $4 AND concluida = FALSE AND deletado_em IS NULL;
        """
        status = await conn.execute(
            sql,
            dados["descricao_servico"].strip(),
            dados["data_agendada"],
            dados["tipo_manutencao"],
            manutencao_id,
        )
        return status == "UPDATE 1"
    except Exception as e:
        print(f"Erro ao atualizar manutenção: {e}")
        return False


async def concluir_ordem_manutencao(
    conn: asyncpg.Connection, manutencao_id: int, funcionario_id: int
) -> bool:
    try:
        sql = """
            UPDATE manutencao_preventiva
            SET concluida = TRUE,
                data_conclusao_real = NOW(),
                funcionario_id = $1
            WHERE id = $2 AND concluida = FALSE;
        """
        status = await conn.execute(sql, funcionario_id, manutencao_id)
        return status == "UPDATE 1"
    except Exception as e:
        print(f"Erro ao concluir ordem de manutenção: {e}")
        return False


async def soft_delete_manutencao(conn: asyncpg.Connection, manutencao_id: int) -> bool:
    try:
        sql = """
            UPDATE manutencao_preventiva 
            SET deletado_em = NOW() 
            WHERE id = $1 AND concluida = FALSE AND deletado_em IS NULL;
        """
        status = await conn.execute(sql, manutencao_id)
        return status == "UPDATE 1"
    except Exception as e:
        print(f"Erro ao aplicar soft delete na manutenção: {e}")
        return False
