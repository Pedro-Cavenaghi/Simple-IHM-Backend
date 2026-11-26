# Teste 1
import json

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


async def listar_logs_auditoria(
    conn: asyncpg.Connection, usuario_id: int | None = None, limite: int = 100
) -> list[dict]:
    """
    Retorna os registros de auditoria com INNER/LEFT JOIN trazendo
    o nome e e-mail do usuário que executou a ação.
    """
    try:
        sql = """
            SELECT 
                a.id,
                a.usuario_id,
                f.nome AS usuario_nome,
                f.email AS usuario_email,
                f.perfil AS usuario_perfil,
                a.acao,
                a.entidade,
                a.entidade_id,
                a.detalhes,
                a.criado_em
            FROM public.audit_logs a
            LEFT JOIN public.funcionarios f ON a.usuario_id = f.id
            WHERE ($1::INT IS NULL OR a.usuario_id = $1)
            ORDER BY a.criado_em DESC
            LIMIT $2;
        """
        registros = await conn.fetch(sql, usuario_id, limite)
        return [dict(row) for row in registros]
    except Exception as e:
        print(f"Erro ao listar logs de auditoria: {e}")
        return []


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


async def listar_maquinas_para_dispositivos(conn: asyncpg.Connection):
    """Lista as máquinas ativas indicando se há manutenção em andamento.

    Uma máquina está em manutenção quando possui uma ordem não concluída
    cuja data agendada já chegou (ordens futuras não travam a máquina).
    """
    try:
        sql = """
            SELECT
                m.id,
                m.tag_maquina,
                m.nome_maquina,
                m.setor,
                EXISTS (
                    SELECT 1
                    FROM manutencao_preventiva mp
                    WHERE mp.maquina_id = m.id
                      AND mp.concluida = FALSE
                      AND mp.deletado_em IS NULL
                      AND mp.data_agendada <= CURRENT_DATE
                ) AS em_manutencao
            FROM maquinas m
            WHERE m.deletado_em IS NULL
            ORDER BY m.tag_maquina ASC;
        """
        registros = await conn.fetch(sql)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar máquinas para dispositivos no Repository: {e}")
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


async def agendar_manutencao(conn: asyncpg.Connection, dados: dict) -> dict | None:
    try:
        maquina_ativa = await conn.fetchval(
            "SELECT id FROM maquinas WHERE id = $1 AND deletado_em IS NULL;",
            dados["maquina_id"],
        )
        if not maquina_ativa:
            return None

        sql = """
            INSERT INTO manutencao_preventiva (maquina_id, descricao_servico, data_agendada, tipo_manutencao)
            VALUES ($1, $2, $3, $4)
            RETURNING id, maquina_id, descricao_servico, data_agendada, tipo_manutencao, concluida, data_conclusao_real, funcionario_id;
        """
        registro = await conn.fetchrow(
            sql,
            dados["maquina_id"],
            dados["descricao_servico"].strip(),
            dados["data_agendada"],
            dados["tipo_manutencao"],
        )
        return dict(registro) if registro else None
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
            WHERE mp.deletado_em IS NULL AND (m.deletado_em IS NULL OR m.id IS NULL)
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
            WHERE id = $2 AND concluida = FALSE AND deletado_em IS NULL;
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


# ==========================================
# ALERTAS DO MACHINE LEARNING
# ==========================================

SQL_ALERTA = """
    SELECT
        a.id, a.maquina_id, m.tag_maquina, m.nome_maquina,
        a.diagnostico, a.confianca, a.pontuacao, a.severidade, a.mensagem,
        a.minutos_ate_limite, a.criado_em, a.atualizado_em, a.encerrado_em,
        a.reconhecido_em, a.reconhecido_por, f.nome AS reconhecido_por_nome,
        a.manutencao_id, a.manutencao_status, a.manutencao_descricao,
        a.manutencao_data_sugerida, a.analisado_por,
        analista.nome AS analisado_por_nome, a.analisado_em, a.analise_observacao,
        a.linha_de_base
    FROM alertas a
    JOIN maquinas m ON m.id = a.maquina_id
    LEFT JOIN funcionarios f ON f.id = a.reconhecido_por
    LEFT JOIN funcionarios analista ON analista.id = a.analisado_por
"""


async def _solicitar_manutencao(
    conn: asyncpg.Connection, alerta_id: int, descricao: str | None
) -> None:
    """Abre ou atualiza a solicitação pendente do alerta.

    Não abre outra se a máquina já tem solicitação pendente ou ordem em aberto
    para o MESMO diagnóstico: uma falha diferente sempre gera sua solicitação.
    Nunca altera uma solicitação já analisada. Severidade alta sugere hoje, as
    demais amanhã, e a data sugerida nunca é adiada.
    """
    if not descricao:
        return
    sql = """
        UPDATE alertas a
        SET manutencao_status = 'pendente',
            manutencao_descricao = $2::text,
            manutencao_data_sugerida = LEAST(
                a.manutencao_data_sugerida,
                CURRENT_DATE + CASE WHEN a.severidade = 'alta' THEN 0 ELSE 1 END
            )
        WHERE a.id = $1
          AND a.diagnostico IS NOT NULL
          AND (
            a.manutencao_status = 'pendente'
            OR (
                a.manutencao_status IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM alertas outro
                    WHERE outro.maquina_id = a.maquina_id
                      AND outro.id <> a.id
                      AND outro.diagnostico = a.diagnostico
                      AND outro.manutencao_status = 'pendente'
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM alertas origem
                    JOIN manutencao_preventiva mp ON mp.id = origem.manutencao_id
                    WHERE origem.maquina_id = a.maquina_id
                      AND origem.diagnostico = a.diagnostico
                      AND mp.concluida = FALSE
                      AND mp.deletado_em IS NULL
                )
            )
          );
    """
    await conn.execute(sql, alerta_id, descricao)


async def obter_alerta(conn: asyncpg.Connection, alerta_id: int) -> dict | None:
    try:
        registro = await conn.fetchrow(SQL_ALERTA + " WHERE a.id = $1;", alerta_id)
        return dict(registro) if registro else None
    except Exception as e:
        print(f"Erro ao obter alerta: {e}")
        return None


async def listar_alertas(
    conn: asyncpg.Connection,
    maquina_id: int | None = None,
    apenas_abertos: bool = False,
    limite: int = 100,
) -> list[dict]:
    try:
        sql = (
            SQL_ALERTA
            + """
            WHERE ($1::int IS NULL OR a.maquina_id = $1)
              AND (NOT $2::boolean OR a.encerrado_em IS NULL)
            ORDER BY a.criado_em DESC
            LIMIT $3;
        """
        )
        registros = await conn.fetch(sql, maquina_id, apenas_abertos, limite)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar alertas: {e}")
        return []


async def criar_alerta(conn: asyncpg.Connection, dados: dict) -> dict | None:
    try:
        sql = """
            INSERT INTO alertas
            (maquina_id, diagnostico, confianca, pontuacao, severidade,
             mensagem, minutos_ate_limite, linha_de_base)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            RETURNING id;
        """
        base = dados.get("linha_de_base")
        # Tudo ou nada: um alerta órfão bloquearia a máquina no índice de alerta aberto
        async with conn.transaction():
            alerta_id = await conn.fetchval(
                sql,
                dados["maquina_id"],
                dados.get("diagnostico"),
                dados.get("confianca"),
                dados.get("pontuacao", 0.0),
                dados.get("severidade", "media"),
                dados["mensagem"],
                dados.get("minutos_ate_limite"),
                None if base is None else json.dumps(base),
            )
            await _solicitar_manutencao(
                conn, alerta_id, dados.get("manutencao_descricao")
            )
        return await obter_alerta(conn, alerta_id)
    except Exception as e:
        print(f"Erro ao criar alerta: {e}")
        return None


async def atualizar_alerta(
    conn: asyncpg.Connection, alerta_id: int, dados: dict
) -> dict | None:
    """Atualiza o diagnóstico de um alerta ainda aberto."""
    try:
        sql = """
            UPDATE alertas
            SET diagnostico = $2, confianca = $3, pontuacao = $4,
                severidade = $5, mensagem = $6, minutos_ate_limite = $7,
                atualizado_em = NOW()
            WHERE id = $1 AND encerrado_em IS NULL
            RETURNING id;
        """
        async with conn.transaction():
            atualizado = await conn.fetchval(
                sql,
                alerta_id,
                dados.get("diagnostico"),
                dados.get("confianca"),
                dados.get("pontuacao", 0.0),
                dados.get("severidade", "media"),
                dados["mensagem"],
                dados.get("minutos_ate_limite"),
            )
            if not atualizado:
                return None
            await _solicitar_manutencao(
                conn, alerta_id, dados.get("manutencao_descricao")
            )
        return await obter_alerta(conn, alerta_id)
    except Exception as e:
        print(f"Erro ao atualizar alerta: {e}")
        return None


async def encerrar_alerta(conn: asyncpg.Connection, alerta_id: int) -> dict | None:
    try:
        sql = """
            UPDATE alertas
            SET encerrado_em = NOW(), atualizado_em = NOW()
            WHERE id = $1 AND encerrado_em IS NULL
            RETURNING id;
        """
        encerrado = await conn.fetchval(sql, alerta_id)
        return await obter_alerta(conn, alerta_id) if encerrado else None
    except Exception as e:
        print(f"Erro ao encerrar alerta: {e}")
        return None


async def reconhecer_alerta(
    conn: asyncpg.Connection, alerta_id: int, usuario_id: int
) -> dict | None:
    """Marca que alguém viu o alerta. Retorna None se já tinha sido reconhecido."""
    try:
        sql = """
            UPDATE alertas
            SET reconhecido_em = NOW(), reconhecido_por = $2
            WHERE id = $1 AND reconhecido_em IS NULL
            RETURNING id;
        """
        reconhecido = await conn.fetchval(sql, alerta_id, usuario_id)
        return await obter_alerta(conn, alerta_id) if reconhecido else None
    except Exception as e:
        print(f"Erro ao reconhecer alerta: {e}")
        return None


async def listar_solicitacoes_manutencao(
    conn: asyncpg.Connection, status: str = "pendente", limite: int = 100
) -> list[dict]:
    try:
        sql = (
            SQL_ALERTA
            + """
            WHERE a.manutencao_status = $1 AND m.deletado_em IS NULL
            ORDER BY a.manutencao_data_sugerida ASC, a.criado_em DESC
            LIMIT $2;
        """
        )
        registros = await conn.fetch(sql, status, limite)
        return [dict(r) for r in registros]
    except Exception as e:
        print(f"Erro ao listar solicitações de manutenção: {e}")
        return []


async def aprovar_manutencao_alerta( 
    conn: asyncpg.Connection,
    alerta_id: int,
    usuario_id: int,
    descricao: str | None = None,
    data_agendada: date | None = None,
    observacao: str | None = None,
) -> dict | None:
    """Aprova a solicitação e cria a ordem preditiva, tudo ou nada.

    Retorna None se a solicitação não está pendente ou a máquina foi removida.
    """
    try:
        async with conn.transaction():
            solicitacao = await conn.fetchrow(
                """
                UPDATE alertas a
                SET manutencao_status = 'aprovada',
                    manutencao_descricao = COALESCE($3::text, a.manutencao_descricao),
                    manutencao_data_sugerida =
                        COALESCE($4::date, a.manutencao_data_sugerida),
                    analisado_por = $2,
                    analisado_em = NOW(),
                    analise_observacao = $5::text,
                    atualizado_em = NOW()
                FROM maquinas m
                WHERE a.id = $1
                  AND m.id = a.maquina_id
                  AND m.deletado_em IS NULL
                  AND a.manutencao_status = 'pendente'
                RETURNING a.maquina_id, a.manutencao_descricao,
                          a.manutencao_data_sugerida;
                """,
                alerta_id,
                usuario_id,
                descricao.strip() if descricao else None,
                data_agendada,
                observacao,
            )
            if not solicitacao:
                return None

            manutencao_id = await conn.fetchval(
                """
                INSERT INTO manutencao_preventiva
                (maquina_id, descricao_servico, data_agendada, tipo_manutencao)
                VALUES ($1, $2, $3, 'Preditiva')
                RETURNING id;
                """,
                solicitacao["maquina_id"],
                solicitacao["manutencao_descricao"],
                solicitacao["manutencao_data_sugerida"],
            )
            await conn.execute(
                "UPDATE alertas SET manutencao_id = $2 WHERE id = $1;",
                alerta_id,
                manutencao_id,
            )
        return await obter_alerta(conn, alerta_id)
    except Exception as e:
        print(f"Erro ao aprovar manutenção do alerta: {e}")
        return None


async def rejeitar_manutencao_alerta(
    conn: asyncpg.Connection, alerta_id: int, usuario_id: int, observacao: str
) -> dict | None:
    """Rejeita a solicitação. Retorna None se ela não está pendente."""
    try:
        rejeitado = await conn.fetchval(
            """
            UPDATE alertas
            SET manutencao_status = 'rejeitada',
                analisado_por = $2,
                analisado_em = NOW(),
                analise_observacao = $3,
                atualizado_em = NOW()
            WHERE id = $1 AND manutencao_status = 'pendente'
            RETURNING id;
            """,
            alerta_id,
            usuario_id,
            observacao.strip(),
        )
        return await obter_alerta(conn, alerta_id) if rejeitado else None
    except Exception as e:
        print(f"Erro ao rejeitar manutenção do alerta: {e}")
        return None


async def buscar_leituras_recentes(
    conn: asyncpg.Connection, maquina_id: int, limite: int, horas: int = 2
) -> list[dict]:
    """Últimas leituras com a máquina em operação, em ordem cronológica.

    Usado pelo monitor de ML para não começar "às cegas" depois de um deploy.
    Ignora os períodos de alerta, para a falha não contaminar a linha de base.
    """
    try:
        sql = """
            SELECT tensao_volt, corrente_ampere, potencia_watt,
                   vibracao_rms, frequencia_hz
            FROM logs_maquinas
            WHERE maquina_id = $1
              AND status_no_momento = 'Ativa'
              AND horario_do_log >= NOW() - make_interval(hours => $3)
              AND NOT EXISTS (
                  SELECT 1 FROM alertas a
                  WHERE a.maquina_id = logs_maquinas.maquina_id
                    AND logs_maquinas.horario_do_log >= a.criado_em
                    AND logs_maquinas.horario_do_log
                        <= COALESCE(a.encerrado_em, NOW())
              )
            ORDER BY horario_do_log DESC, id DESC
            LIMIT $2;
        """
        registros = await conn.fetch(sql, maquina_id, limite, horas)
        return [dict(r) for r in reversed(registros)]
    except Exception as e:
        print(f"Erro ao buscar leituras recentes: {e}")
        return []
