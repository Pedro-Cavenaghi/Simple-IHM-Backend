-- Alertas gerados pelo monitor de machine learning (app/monitor.py).
-- Idempotente: a API aplica este arquivo a cada inicialização.

CREATE TABLE IF NOT EXISTS public.alertas (
    id serial PRIMARY KEY,
    maquina_id integer NOT NULL REFERENCES public.maquinas (id),
    -- Falha mais provável segundo a árvore de decisão (NULL se ainda indefinida)
    diagnostico character varying(30),
    -- Fração das leituras do alerta que votaram nesse diagnóstico (0 a 1)
    confianca real,
    -- Maior pontuação de anomalia do Isolation Forest durante o alerta (> 0 = anômalo)
    pontuacao real NOT NULL DEFAULT 0,
    severidade character varying(10) NOT NULL DEFAULT 'media',
    mensagem text NOT NULL,
    -- Prognóstico da regressão: minutos até a vibração atingir o limite
    minutos_ate_limite real,
    criado_em timestamp with time zone NOT NULL DEFAULT now(),
    atualizado_em timestamp with time zone NOT NULL DEFAULT now(),
    -- Preenchido quando a máquina volta ao normal
    encerrado_em timestamp with time zone,
    reconhecido_em timestamp with time zone,
    reconhecido_por integer REFERENCES public.funcionarios (id) ON DELETE SET NULL,
    -- Manutenção preditiva criada a partir do alerta (fase 4)
    manutencao_id integer REFERENCES public.manutencao_preventiva (id) ON DELETE SET NULL,
    CONSTRAINT check_alerta_severidade CHECK (severidade IN ('baixa', 'media', 'alta'))
);

CREATE INDEX IF NOT EXISTS idx_alertas_maquina_criado
    ON public.alertas (maquina_id, criado_em DESC);

-- No máximo um alerta aberto por máquina
CREATE UNIQUE INDEX IF NOT EXISTS idx_alertas_um_aberto_por_maquina
    ON public.alertas (maquina_id)
    WHERE encerrado_em IS NULL;
