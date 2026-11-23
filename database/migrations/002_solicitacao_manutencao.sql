-- Solicitação de manutenção preditiva gerada a partir de um alerta do ML.
-- A ordem em manutencao_preventiva só é criada quando ADMIN ou MANUTENCAO aprova.
-- Idempotente: a API aplica este arquivo a cada inicialização.

ALTER TABLE public.alertas
    -- NULL = sem solicitação (ainda sem diagnóstico ou já coberto por outra)
    ADD COLUMN IF NOT EXISTS manutencao_status character varying(10)
        CONSTRAINT check_alerta_manutencao_status
        CHECK (manutencao_status IN ('pendente', 'aprovada', 'rejeitada')),
    ADD COLUMN IF NOT EXISTS manutencao_descricao text,
    ADD COLUMN IF NOT EXISTS manutencao_data_sugerida date,
    ADD COLUMN IF NOT EXISTS analisado_por integer
        REFERENCES public.funcionarios (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS analisado_em timestamp with time zone,
    ADD COLUMN IF NOT EXISTS analise_observacao text;

CREATE INDEX IF NOT EXISTS idx_alertas_manutencao_pendente
    ON public.alertas (maquina_id)
    WHERE manutencao_status = 'pendente';
