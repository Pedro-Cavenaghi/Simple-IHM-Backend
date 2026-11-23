-- Referência da máquina congelada quando o alerta abriu (um valor por sinal).
-- Mantém a comparação correta em falhas longas, mesmo depois de um redeploy.
-- Idempotente: a API aplica este arquivo a cada inicialização.

ALTER TABLE public.alertas
    ADD COLUMN IF NOT EXISTS linha_de_base jsonb;
