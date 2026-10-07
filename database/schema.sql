CREATE TABLE IF NOT EXISTS maquinas (
    id SERIAL PRIMARY KEY,
    tag_maquina VARCHAR(20) NOT NULL,
    nome_maquina VARCHAR(100) NOT NULL,
    setor VARCHAR(50),
    data_cadastro TIMESTAMP NOT NULL DEFAULT NOW(),
    ultima_atualizacao TIMESTAMP,
    deletado_em TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_maquinas_tag_ativa
ON maquinas (UPPER(tag_maquina))
WHERE deletado_em IS NULL;


CREATE TABLE IF NOT EXISTS funcionarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cargo VARCHAR(50) NOT NULL,
    turno_trabalho INTEGER NOT NULL CHECK (turno_trabalho BETWEEN 1 AND 3),
    email VARCHAR(255) NOT NULL,
    senha_hash TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    deletado_em TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_funcionarios_email_ativo
ON funcionarios (LOWER(email))
WHERE deletado_em IS NULL;


CREATE TABLE IF NOT EXISTS status_atual_maquinas (
    maquina_id INTEGER PRIMARY KEY
        REFERENCES maquinas(id) ON DELETE CASCADE,

    status_atual VARCHAR(20) NOT NULL
        CHECK (
            status_atual IN (
                'Ativa',
                'Inativa',
                'Desligada',
                'Manutenção'
            )
        ),

    vibracao_rms DOUBLE PRECISION NOT NULL CHECK (vibracao_rms >= 0),
    corrente_ampere DOUBLE PRECISION NOT NULL CHECK (corrente_ampere >= 0),

    tensao_volt DOUBLE PRECISION NOT NULL
        CHECK (tensao_volt >= 0 AND tensao_volt <= 250),

    potencia_watt DOUBLE PRECISION NOT NULL CHECK (potencia_watt >= 0),

    frequencia_hz DOUBLE PRECISION NOT NULL
        CHECK (frequencia_hz >= 0 AND frequencia_hz <= 100),

    momento_da_leitura TIMESTAMP NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS logs_maquinas (
    id BIGSERIAL PRIMARY KEY,

    horario_do_log TIMESTAMP NOT NULL DEFAULT NOW(),

    maquina_id INTEGER NOT NULL
        REFERENCES maquinas(id),

    turno INTEGER CHECK (turno BETWEEN 1 AND 3),

    vibracao_rms DOUBLE PRECISION NOT NULL CHECK (vibracao_rms >= 0),
    corrente_ampere DOUBLE PRECISION NOT NULL CHECK (corrente_ampere >= 0),

    tensao_volt DOUBLE PRECISION NOT NULL
        CHECK (tensao_volt >= 0 AND tensao_volt <= 250),

    potencia_watt DOUBLE PRECISION NOT NULL CHECK (potencia_watt >= 0),

    status_no_momento VARCHAR(20) NOT NULL
        CHECK (
            status_no_momento IN (
                'Ativa',
                'Inativa',
                'Desligada',
                'Manutenção'
            )
        ),

    frequencia_hz DOUBLE PRECISION NOT NULL
        CHECK (frequencia_hz >= 0 AND frequencia_hz <= 100)
);


CREATE TABLE IF NOT EXISTS manutencao_preventiva (
    id SERIAL PRIMARY KEY,

    maquina_id INTEGER
        REFERENCES maquinas(id) ON DELETE SET NULL,

    descricao_servico TEXT NOT NULL,

    data_agendada DATE NOT NULL,

    concluida BOOLEAN NOT NULL DEFAULT FALSE,

    data_conclusao_real TIMESTAMP,

    funcionario_id INTEGER
        REFERENCES funcionarios(id) ON DELETE SET NULL,

    tipo_manutencao VARCHAR(20) NOT NULL
        CHECK (
            tipo_manutencao IN (
                'Preventiva',
                'Preditiva'
            )
        ),

    deletado_em TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_logs_maquina_horario
ON logs_maquinas (maquina_id, horario_do_log DESC);

CREATE INDEX IF NOT EXISTS idx_manutencao_maquina
ON manutencao_preventiva (maquina_id);

CREATE INDEX IF NOT EXISTS idx_manutencao_data
ON manutencao_preventiva (data_agendada);