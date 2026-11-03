--
-- PostgreSQL database dump
--

\restrict 4PJxnYOZlSKSf1oJyP83vyg40yc3IQ9lvnnOHUoUIDoATQdaNDP4uHTJonyWAf0

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    usuario_id integer,
    acao character varying(50) NOT NULL,
    entidade character varying(50) NOT NULL,
    entidade_id integer,
    detalhes text,
    criado_em timestamp with time zone DEFAULT now()
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: funcionarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.funcionarios (
    id integer NOT NULL,
    nome character varying(100) NOT NULL,
    cargo character varying(50),
    data_cadastro timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deletado_em timestamp without time zone,
    email character varying(100) DEFAULT 'provisorio@empresa.com'::character varying NOT NULL,
    senha_hash character varying(255) DEFAULT 'mudar_no_primeiro_acesso'::character varying NOT NULL,
    ultima_atualizacao timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    turno_trabalho integer DEFAULT 1 NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    perfil character varying(20) DEFAULT 'OPERADOR'::character varying NOT NULL,
    CONSTRAINT check_funcionario_perfil CHECK (((perfil)::text = ANY (ARRAY[('ADMIN'::character varying)::text, ('OPERADOR'::character varying)::text, ('MANUTENCAO'::character varying)::text]))),
    CONSTRAINT check_turno_trabalho CHECK ((turno_trabalho = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: funcionarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.funcionarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: funcionarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.funcionarios_id_seq OWNED BY public.funcionarios.id;


--
-- Name: logs_maquinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logs_maquinas (
    id bigint NOT NULL,
    horario_do_log timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    maquina_id integer,
    turno integer,
    vibracao_rms real,
    corrente_ampere real,
    tensao_volt real,
    potencia_watt real,
    status_no_momento character varying(20) NOT NULL,
    frequencia_hz real DEFAULT 0,
    CONSTRAINT logs_maquinas_turno_check CHECK ((turno = ANY (ARRAY[1, 2, 3])))
);


--
-- Name: logs_maquinas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logs_maquinas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logs_maquinas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logs_maquinas_id_seq OWNED BY public.logs_maquinas.id;


--
-- Name: manutencao_preventiva; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manutencao_preventiva (
    id integer NOT NULL,
    maquina_id integer,
    descricao_servico text,
    data_agendada date NOT NULL,
    concluida boolean DEFAULT false,
    data_conclusao_real timestamp without time zone,
    funcionario_id integer,
    tipo_manutencao character varying(20) DEFAULT 'Preventiva'::character varying NOT NULL,
    deletado_em timestamp without time zone,
    CONSTRAINT check_tipo_manutencao CHECK (((tipo_manutencao)::text = ANY (ARRAY[('Preventiva'::character varying)::text, ('Preditiva'::character varying)::text])))
);


--
-- Name: manutencao_preventiva_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manutencao_preventiva_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manutencao_preventiva_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manutencao_preventiva_id_seq OWNED BY public.manutencao_preventiva.id;


--
-- Name: maquinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.maquinas (
    id integer NOT NULL,
    tag_maquina character varying(20) NOT NULL,
    nome_maquina character varying(100) NOT NULL,
    setor character varying(50),
    data_cadastro timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    ultima_atualizacao timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deletado_em timestamp without time zone
);


--
-- Name: maquinas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.maquinas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: maquinas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.maquinas_id_seq OWNED BY public.maquinas.id;


--
-- Name: status_atual_maquinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.status_atual_maquinas (
    momento_da_leitura timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    maquina_id integer NOT NULL,
    vibracao_rms real DEFAULT 0,
    corrente_ampere real DEFAULT 0,
    tensao_volt real DEFAULT 0,
    potencia_watt real DEFAULT 0,
    status_atual character varying(20) DEFAULT 'Desligada'::character varying,
    frequencia_hz real DEFAULT 0,
    CONSTRAINT status_atual_maquinas_status_atual_check CHECK (((status_atual)::text = ANY (ARRAY[('Ativa'::character varying)::text, ('Inativa'::character varying)::text, ('Desligada'::character varying)::text, ('Manutenção'::character varying)::text])))
)
WITH (fillfactor='80', autovacuum_vacuum_scale_factor='0.0', autovacuum_vacuum_threshold='50');


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: funcionarios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.funcionarios ALTER COLUMN id SET DEFAULT nextval('public.funcionarios_id_seq'::regclass);


--
-- Name: logs_maquinas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_maquinas ALTER COLUMN id SET DEFAULT nextval('public.logs_maquinas_id_seq'::regclass);


--
-- Name: manutencao_preventiva id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manutencao_preventiva ALTER COLUMN id SET DEFAULT nextval('public.manutencao_preventiva_id_seq'::regclass);


--
-- Name: maquinas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maquinas ALTER COLUMN id SET DEFAULT nextval('public.maquinas_id_seq'::regclass);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: funcionarios funcionarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.funcionarios
    ADD CONSTRAINT funcionarios_pkey PRIMARY KEY (id);


--
-- Name: logs_maquinas logs_maquinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_maquinas
    ADD CONSTRAINT logs_maquinas_pkey PRIMARY KEY (id);


--
-- Name: manutencao_preventiva manutencao_preventiva_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manutencao_preventiva
    ADD CONSTRAINT manutencao_preventiva_pkey PRIMARY KEY (id);


--
-- Name: maquinas maquinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maquinas
    ADD CONSTRAINT maquinas_pkey PRIMARY KEY (id);


--
-- Name: idx_maquinas_tag_maquina_ativa; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_maquinas_tag_maquina_ativa
    ON public.maquinas (UPPER(tag_maquina))
    WHERE deletado_em IS NULL;

--
-- Name: status_atual_maquinas status_atual_maquinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_atual_maquinas
    ADD CONSTRAINT status_atual_maquinas_pkey PRIMARY KEY (maquina_id);


--
-- Name: idx_funcionarios_ativos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_funcionarios_ativos ON public.funcionarios USING btree (id) WHERE (deletado_em IS NULL);


--
-- Name: idx_funcionarios_email_ativo; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_funcionarios_email_ativo ON public.funcionarios USING btree (lower((email)::text)) WHERE (deletado_em IS NULL);


--
-- Name: idx_logs_maquina_tempo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_maquina_tempo ON public.logs_maquinas USING btree (maquina_id, horario_do_log DESC);


--
-- Name: idx_manutencoes_abertas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_manutencoes_abertas ON public.manutencao_preventiva USING btree (data_agendada) WHERE (concluida = false);


--
-- Name: audit_logs audit_logs_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.funcionarios(id) ON DELETE SET NULL;


--
-- Name: logs_maquinas logs_maquinas_maquina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_maquinas
    ADD CONSTRAINT logs_maquinas_maquina_id_fkey FOREIGN KEY (maquina_id) REFERENCES public.maquinas(id);


--
-- Name: manutencao_preventiva manutencao_preventiva_funcionario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manutencao_preventiva
    ADD CONSTRAINT manutencao_preventiva_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES public.funcionarios(id) ON DELETE RESTRICT;


--
-- Name: manutencao_preventiva manutencao_preventiva_maquina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manutencao_preventiva
    ADD CONSTRAINT manutencao_preventiva_maquina_id_fkey FOREIGN KEY (maquina_id) REFERENCES public.maquinas(id);


--
-- Name: status_atual_maquinas status_atual_maquinas_maquina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.status_atual_maquinas
    ADD CONSTRAINT status_atual_maquinas_maquina_id_fkey FOREIGN KEY (maquina_id) REFERENCES public.maquinas(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 4PJxnYOZlSKSf1oJyP83vyg40yc3IQ9lvnnOHUoUIDoATQdaNDP4uHTJonyWAf0
