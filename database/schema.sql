-- Schema de teste alinhado ao dump monitoramento_industrial de 2026-10-06.
-- Mantém audit_logs, pois essa tabela foi adicionada posteriormente no backend.
-- Não contém dados reais, usuários, hashes, roles ou configurações do cluster.

CREATE TABLE IF NOT EXISTS maquinas (
    id SERIAL PRIMARY KEY,
    tag_maquina VARCHAR(20) NOT NULL,
    nome_maquina VARCHAR(100) NOT NULL,
    setor VARCHAR(50),
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deletado_em TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_maquinas_tag_ativa
ON maquinas (UPPER(tag_maquina))
WHERE deletado_em IS NULL;

CREATE TABLE IF NOT EXISTS funcionarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cargo VARCHAR(50),
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deletado_em TIMESTAMP,
    email VARCHAR(100) NOT NULL DEFAULT 'provisorio@empresa.com',
    senha_hash VARCHAR(255) NOT NULL DEFAULT 'mudar_no_primeiro_acesso',
    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    turno_trabalho INTEGER NOT NULL DEFAULT 1
        CHECK (turno_trabalho IN (1, 2, 3)),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    perfil VARCHAR(20) NOT NULL DEFAULT 'OPERADOR'
        CHECK (perfil IN ('ADMIN', 'OPERADOR', 'MANUTENCAO'))
);

CREATE INDEX IF NOT EXISTS idx_funcionarios_ativos
ON funcionarios (id)
WHERE deletado_em IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_funcionarios_email_ativo
ON funcionarios (LOWER(email))
WHERE deletado_em IS NULL;

-- Esta tabela não aparece no dump de 2026-10-06.
-- Foi preservada porque o backend atual já possui serviço de auditoria.
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    usuario_id INTEGER
        REFERENCES funcionarios(id) ON DELETE SET NULL,
    acao VARCHAR(100) NOT NULL,
    entidade VARCHAR(100) NOT NULL,
    entidade_id INTEGER,
    detalhes TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS status_atual_maquinas (
    momento_da_leitura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    maquina_id INTEGER PRIMARY KEY
        REFERENCES maquinas(id),
    vibracao_rms REAL DEFAULT 0,
    corrente_ampere REAL DEFAULT 0,
    tensao_volt REAL DEFAULT 0,
    potencia_watt REAL DEFAULT 0,
    status_atual VARCHAR(20) DEFAULT 'Desligada'
        CHECK (
            status_atual IN (
                'Ativa',
                'Inativa',
                'Desligada',
                'Manutenção'
            )
        ),
    frequencia_hz REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS logs_maquinas (
    id BIGSERIAL PRIMARY KEY,
    horario_do_log TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    maquina_id INTEGER
        REFERENCES maquinas(id),
    turno INTEGER
        CHECK (turno IN (1, 2, 3)),
    vibracao_rms REAL,
    corrente_ampere REAL,
    tensao_volt REAL,
    potencia_watt REAL,
    status_no_momento VARCHAR(20) NOT NULL,
    frequencia_hz REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_logs_maquina_tempo
ON logs_maquinas (maquina_id, horario_do_log DESC);

CREATE TABLE IF NOT EXISTS manutencao_preventiva (
    id SERIAL PRIMARY KEY,
    maquina_id INTEGER
        REFERENCES maquinas(id),
    descricao_servico TEXT,
    data_agendada DATE NOT NULL,
    concluida BOOLEAN DEFAULT FALSE,
    data_conclusao_real TIMESTAMP,
    funcionario_id INTEGER
        REFERENCES funcionarios(id) ON DELETE RESTRICT,
    tipo_manutencao VARCHAR(20) NOT NULL DEFAULT 'Preventiva'
        CHECK (
            tipo_manutencao IN (
                'Preventiva',
                'Preditiva'
            )
        ),
    deletado_em TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_manutencoes_abertas
ON manutencao_preventiva (data_agendada)
WHERE concluida = FALSE;
