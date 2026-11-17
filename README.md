<div align="center">

# ⚙️ Simple IHM — Backend

### API de Telemetria Industrial em Tempo Real

*Ecossistema IoT para monitoramento de máquinas, manutenção preventiva/preditiva e controle de acesso por perfil.*

[![Backend Pipeline](https://github.com/Pedro-Cavenaghi/Simple-IHM-Backend/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Pedro-Cavenaghi/Simple-IHM-Backend/actions/workflows/pipeline.yml)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?style=flat&logo=postgresql&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-tempo%20real-8A2BE2?style=flat)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat&logo=docker&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat&logo=railway&logoColor=white)

[**📖 Documentação da API (Swagger)**](https://simple-ihm-api-production.up.railway.app/docs) &nbsp;•&nbsp; [**🖥️ Repositório do Frontend**](https://github.com/SamukaSantos-DEV/Simple-IHM-Frontend)

<br>

<img src="docs/images/dashboard.png" alt="Dashboard inicial do Simple IHM" width="900">

<sub>Dashboard de monitoramento do frontend React, alimentado em tempo real por esta API.</sub>

</div>

---

## 📋 Sumário

- [Sobre o projeto](#-sobre-o-projeto)
- [Arquitetura](#️-arquitetura)
- [Tecnologias](#️-tecnologias)
- [Segurança e perfis de acesso](#-segurança-e-perfis-de-acesso)
- [Endpoints](#️-endpoints)
- [Tempo real com WebSocket](#-tempo-real-com-websocket)
- [Banco de dados](#️-banco-de-dados)
- [Simulador da ESP32](#-simulador-da-esp32)
- [Machine Learning](#-machine-learning)
- [Como executar](#-como-executar)
- [Testes e CI](#-testes-e-ci)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Equipe](#-equipe)

---

## 💡 Sobre o projeto

O **Simple IHM** (*Interface Homem-Máquina*) é um ecossistema IoT para monitorar máquinas industriais em tempo real. Ele aplica conceitos de **manutenção preventiva e preditiva** no chão de fábrica e transforma leituras de sensores em uma interface simples, direta e de baixa carga cognitiva para operadores.

Este repositório contém a **central backend**, responsável por:

- 📡 **Receber telemetria** de microcontroladores ESP32 (corrente, tensão, potência, vibração e frequência);
- ✅ **Validar** cada leitura antes de qualquer gravação;
- 🗄️ **Persistir** o histórico e o estado atual de cada máquina no PostgreSQL;
- ⚡ **Transmitir** as leituras via WebSocket para o dashboard assim que chegam;
- 🔐 **Autenticar** usuários com JWT e **autorizar** cada ação por perfil (RBAC);
- 🧾 **Auditar** logins e alterações feitas no sistema;
- 🛠️ **Gerenciar** máquinas, funcionários e ordens de manutenção.

O **frontend em React** fica no repositório [Simple-IHM-Frontend](https://github.com/SamukaSantos-DEV/Simple-IHM-Frontend) e consome esta API. Os dois serviços estão hospedados no **Railway**.

---

## 🏗️ Arquitetura

```mermaid
flowchart LR
    subgraph Fabrica["🏭 Chão de fábrica"]
        ESP["ESP32 / Simulador NiceGUI<br/>(leitura a cada 2s)"]
    end

    subgraph Railway["☁️ Railway"]
        API["⚙️ FastAPI<br/>(Uvicorn + asyncpg)"]
        ML["🧠 Monitor de ML<br/>(segundo plano)"]
        DB[("🐘 PostgreSQL")]
        FE["🖥️ Frontend React"]
    end

    ESP -- "POST /enviar-dados<br/>X-API-Key" --> API
    API -. "GET /dispositivos/maquinas<br/>(máquinas + manutenção)" .-> ESP
    API -- "INSERT log + UPSERT status<br/>(transação)" --> DB
    API -- "broadcast WebSocket" --> FE
    API -- "cada leitura" --> ML
    ML -- "alertas" --> DB
    ML -- "/ws/alertas" --> FE
    FE -- "REST + JWT Bearer" --> API
```

**Fluxo de uma leitura de sensor:**

1. A ESP32 envia a leitura para `POST /enviar-dados` com o header `X-API-Key`.
2. O **Pydantic** valida os limites físicos (ex.: tensão entre 0 e 250 V, frequência entre 0 e 100 Hz, nenhum valor negativo).
3. Em uma **única transação**, a API grava o registro histórico em `logs_maquinas` e atualiza o estado atual em `status_atual_maquinas` com um *upsert* (`ON CONFLICT`). O turno (1, 2 ou 3) é calculado automaticamente pelo horário.
4. A leitura é enviada via **WebSocket** para todos os dashboards conectados àquela máquina.
5. Depois da resposta à ESP32, o **monitor de machine learning** avalia a leitura em segundo plano e abre, atualiza ou encerra alertas (veja [Machine Learning](#-machine-learning)). A telemetria nunca espera nem depende do ML.

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| **Linguagem** | Python 3.13 |
| **Framework web** | FastAPI + Uvicorn (assíncrono) |
| **Banco de dados** | PostgreSQL 18 |
| **Driver** | asyncpg com pool de conexões (2 a 10) |
| **Validação** | Pydantic v2 + pydantic-settings |
| **Autenticação** | JWT (python-jose) + bcrypt (passlib) |
| **Tempo real** | WebSockets nativos do FastAPI |
| **Simulador** | NiceGUI (painel web em Python) + httpx |
| **Machine Learning** | scikit-learn, pandas, NumPy, Matplotlib, Jupyter |
| **Qualidade** | Ruff (lint + format), pytest, pytest-asyncio, pytest-cov |
| **Infraestrutura** | Docker, Docker Compose, GitHub Actions, Railway |

---

## 🔐 Segurança e perfis de acesso

A API usa **dois mecanismos de autenticação**, um para máquinas e outro para pessoas:

| Quem | Mecanismo | Onde |
|---|---|---|
| 🤖 ESP32 / simulador | Header `X-API-Key` | `POST /enviar-dados` e `GET /dispositivos/maquinas` |
| 👤 Usuários | `Authorization: Bearer <JWT>` (validade de 8 h) | Todas as rotas REST protegidas |
| 🖥️ Dashboard | `?token=<JWT>` no handshake | Rotas WebSocket |

O JWT carrega o ID, o e-mail e o **perfil** do usuário. Cada rota declara quais perfis podem acessá-la:

| Recurso | 👑 ADMIN | 🧑‍🏭 OPERADOR | 🔧 MANUTENCAO |
|---|:---:|:---:|:---:|
| Status e histórico das máquinas | ✅ | ✅ | ✅ |
| Consultar máquinas | ✅ | ✅ | ✅ |
| Criar, editar e excluir máquinas | ✅ | ❌ | ❌ |
| Plano de manutenção | ✅ | ❌ | ✅ |
| Gestão de funcionários | ✅ | ❌ | ❌ |
| Trilha de auditoria | ✅ | ❌ | ❌ |

Outras práticas adotadas:

- 🔑 Senhas armazenadas com **hash bcrypt**;
- 🧾 **Auditoria** de logins (sucesso e falha) e de criações, edições e exclusões;
- 🗑️ **Soft delete** em máquinas, funcionários e manutenções (`deletado_em`), preservando o histórico;
- 📧 E-mail e tag de máquina **únicos sem diferenciar maiúsculas** (índices parciais sobre registros ativos).

---

## 🛣️ Endpoints

> A documentação interativa completa está disponível em [**/docs**](https://simple-ihm-api-production.up.railway.app/docs).

<details open>
<summary><b>🔑 Autenticação</b></summary>

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/login` | Autentica por e-mail e senha e devolve o JWT com os dados do usuário |

</details>

<details>
<summary><b>📡 Telemetria IoT</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `POST` | `/enviar-dados` | API Key | Recebe a leitura dos sensores, grava e transmite em tempo real |
| `GET` | `/dispositivos/maquinas` | API Key | Lista as máquinas para a ESP32/simulador, indicando quais estão em manutenção |
| `GET` | `/status-maquinas` | Todos | Estado atual de todas as máquinas |
| `GET` | `/status-maquinas/{maquina_id}` | Todos | Estado atual de uma máquina |
| `GET` | `/logs` | Todos | Histórico filtrável por máquina e período (`hoje`, `semana`, `mes`, `customizado`) |

</details>

<details>
<summary><b>🏭 Máquinas</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/maquinas` | Todos | Lista as máquinas ativas |
| `GET` | `/maquinas/{maquina_id}` | Todos | Detalhes de uma máquina |
| `POST` | `/maquinas` | ADMIN | Cadastra uma máquina (tag, nome, setor) |
| `PUT` | `/maquinas/{maquina_id}` | ADMIN | Atualiza uma máquina |
| `DELETE` | `/maquinas/{maquina_id}` | ADMIN | Desativa uma máquina (soft delete) |

</details>

<details>
<summary><b>🔧 Plano de manutenção</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/manutencoes` | ADMIN, MANUTENCAO | Lista as ordens com dados da máquina e do técnico |
| `GET` | `/manutencoes/{manutencao_id}` | ADMIN, MANUTENCAO | Detalhes de uma ordem |
| `POST` | `/manutencoes` | ADMIN, MANUTENCAO | Agenda uma manutenção `Preventiva` ou `Preditiva` |
| `PUT` | `/manutencoes/{manutencao_id}` | ADMIN, MANUTENCAO | Atualiza uma ordem |
| `PATCH` | `/manutencoes/{manutencao_id}/concluir` | ADMIN, MANUTENCAO | Conclui a ordem e registra o técnico responsável |
| `DELETE` | `/manutencoes/{manutencao_id}` | ADMIN, MANUTENCAO | Remove uma ordem (soft delete) |

</details>

<details>
<summary><b>👥 Funcionários</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/funcionarios` | ADMIN | Lista os funcionários ativos |
| `GET` | `/funcionarios/{funcionario_id}` | ADMIN | Detalhes de um funcionário |
| `POST` | `/funcionarios` | ADMIN | Cadastra um funcionário com perfil e turno |
| `PUT` | `/funcionarios/{funcionario_id}` | ADMIN | Atualiza um funcionário |
| `DELETE` | `/funcionarios/{funcionario_id}` | ADMIN | Desativa um funcionário (soft delete) |

</details>

<details>
<summary><b>🧠 Alertas de ML</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/alertas` | Todos | Alertas do mais recente ao mais antigo. Filtros: `maquina_id`, `apenas_abertos`, `limite` |
| `GET` | `/alertas/{alerta_id}` | Todos | Detalhes de um alerta |
| `PATCH` | `/alertas/{alerta_id}/reconhecer` | Todos | Registra quem viu o alerta (auditado). Responde `409` se já reconhecido |
| `GET` | `/ml/status` | ADMIN | Se o modelo está carregado, suas métricas e o estado do monitor em cada máquina |

</details>

<details>
<summary><b>🧾 Auditoria</b></summary>

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/auditoria` | ADMIN | Trilha de auditoria, filtrável por usuário (somente leitura) |

</details>

**Exemplo de leitura enviada pela ESP32:**

```http
POST /enviar-dados
X-API-Key: <sua-api-key>
Content-Type: application/json

{
  "maquina_id": 1,
  "status_atual": "Ativa",
  "corrente_ampere": 16.43,
  "tensao_volt": 216.4,
  "potencia_watt": 3023.0,
  "vibracao_rms": 1.90,
  "frequencia_hz": 60.0
}
```

---

## ⚡ Tempo real com WebSocket

| Rota | Recebe |
|---|---|
| `ws://<host>/ws/telemetria/{maquina_id}?token=<JWT>` | Leituras de uma máquina específica |
| `ws://<host>/ws/telemetria?token=<JWT>` | Leituras de todas as máquinas |
| `ws://<host>/ws/alertas?token=<JWT>` | Mudanças nos alertas de machine learning |

O canal de alertas é separado do de telemetria, então as mensagens que o dashboard já recebe não mudaram. Cada mensagem de `/ws/alertas` tem um `tipo` e o alerta completo (o mesmo formato de `GET /alertas/{id}`):

```json
{
  "tipo": "alerta_atualizado",
  "alerta": {
    "id": 2,
    "maquina_id": 1,
    "tag_maquina": "INJ-01",
    "nome_maquina": "Injetora Plastica",
    "diagnostico": "desgaste_rolamento",
    "confianca": 1.0,
    "pontuacao": 0.21,
    "severidade": "alta",
    "mensagem": "Provável desgaste de rolamento (confiança de 100%). A vibração deve chegar ao limite (2× o normal) em ~1 min.",
    "minutos_ate_limite": 1.2,
    "criado_em": "2026-11-17T12:00:00Z",
    "atualizado_em": "2026-11-17T12:00:30Z",
    "encerrado_em": null,
    "reconhecido_em": null,
    "reconhecido_por": null,
    "reconhecido_por_nome": null,
    "manutencao_id": null
  }
}
```

| `tipo` | Quando |
|---|---|
| `alerta_criado` | A máquina saiu do padrão por 10 s seguidos. Nasce com `diagnostico: null` ("diagnóstico em andamento") |
| `alerta_atualizado` | O diagnóstico apareceu ou mudou, ou a cada 30 s de anomalia (confiança e prognóstico atualizados) |
| `alerta_encerrado` | A máquina voltou ao normal por 3 min, ou parou (`Inativa`/`Desligada`/`Manutenção`) |
| `alerta_reconhecido` | Alguém chamou `PATCH /alertas/{id}/reconhecer` |

`diagnostico` assume `desgaste_rolamento`, `sobrecarga`, `queda_tensao` ou `desbalanceamento`. `severidade` é `media` ou `alta` e nunca diminui enquanto o alerta está aberto. `minutos_ate_limite` só existe para desgaste (`0` = a vibração já passou do limite).

O token é validado no handshake. Conexões sem token válido são fechadas com o código `1008` (*policy violation*). Conexões que caem são removidas automaticamente do gerenciador durante o broadcast.

---

## 🗄️ Banco de dados

```mermaid
erDiagram
    maquinas ||--o| status_atual_maquinas : "estado atual"
    maquinas ||--o{ logs_maquinas : "histórico"
    maquinas ||--o{ manutencao_preventiva : "recebe"
    funcionarios ||--o{ manutencao_preventiva : "executa"
    funcionarios ||--o{ audit_logs : "gera"
    maquinas ||--o{ alertas : "gera"
    funcionarios ||--o{ alertas : "reconhece"

    maquinas {
        int id PK
        varchar tag_maquina
        varchar nome_maquina
        varchar setor
        timestamp deletado_em
    }
    status_atual_maquinas {
        int maquina_id PK
        varchar status_atual
        real corrente_ampere
        real tensao_volt
        real potencia_watt
        real vibracao_rms
        real frequencia_hz
    }
    logs_maquinas {
        bigint id PK
        int maquina_id FK
        int turno
        varchar status_no_momento
        timestamp horario_do_log
    }
    manutencao_preventiva {
        int id PK
        int maquina_id FK
        int funcionario_id FK
        varchar tipo_manutencao
        date data_agendada
        bool concluida
    }
    funcionarios {
        int id PK
        varchar email
        varchar perfil
        int turno_trabalho
        timestamp deletado_em
    }
    alertas {
        int id PK
        int maquina_id FK
        varchar diagnostico
        real confianca
        varchar severidade
        real minutos_ate_limite
        timestamptz encerrado_em
        int reconhecido_por FK
    }
    audit_logs {
        int id PK
        int usuario_id FK
        varchar acao
        varchar entidade
        timestamptz criado_em
    }
```

Destaques da modelagem (`database/schema.sql`):

- **`status_atual_maquinas`** guarda uma linha por máquina, atualizada por *upsert* e configurada com `fillfactor=80` e autovacuum agressivo para suportar escritas constantes;
- **`logs_maquinas`** é a série temporal, indexada por `(maquina_id, horario_do_log DESC)` para consultas rápidas de histórico;
- **Constraints `CHECK`** garantem domínios válidos (status, turno, perfil e tipo de manutenção);
- **Índices parciais** aceleram consultas de manutenções abertas e de registros ativos, e garantem **no máximo um alerta aberto por máquina**.

**Migrações:** tabelas criadas depois do dump ficam em `database/migrations/` (hoje, `001_alertas.sql`). Elas são idempotentes (`IF NOT EXISTS`) e a **API as aplica sozinha a cada inicialização**, então um deploy novo no Railway cria o que falta sem passo manual. O `schema.sql` também as inclui, para bancos criados do zero.

---

## 🚀 Como executar

### Pré-requisitos

- Python 3.13+ ou Docker
- PostgreSQL (local ou via Docker)

### Variáveis de ambiente

Crie um arquivo `.env` na raiz:

```env
# Opção 1: URL completa (usada no Railway)
DATABASE_URL=postgresql://usuario:senha@host:5432/monitoramento_industrial

# Opção 2: credenciais separadas (usadas quando DATABASE_URL não existe)
DB_USER=usuario
DB_PASSWORD=senha
DB_HOST=localhost
DB_PORT=5432
DB_NAME=monitoramento_industrial

# Segurança (defina valores próprios em produção)
SECRET_KEY=troque-por-uma-chave-forte
API_KEY=troque-pela-chave-da-esp32
```

### 🐳 Com Docker Compose

```bash
docker compose up --build
```

Sobe o PostgreSQL 18, a API em `http://localhost:8000` e o simulador em `http://localhost:8081`.

### 🐍 Localmente

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
psql -U usuario -d monitoramento_industrial -f database/schema.sql
uvicorn app.main:app --reload
```

Acesse a documentação em **http://127.0.0.1:8000/docs**.

---

## 🤖 Simulador da ESP32

<div align="center">
<img src="docs/images/simulador.png" alt="Painel do simulador da ESP32" width="900">
</div>

<br>

O simulador (`simulador/`) faz o papel das ESP32 do chão de fábrica: um **painel web em NiceGUI** onde cada máquina tem sliders de tensão, corrente, fator de potência, vibração e frequência. Ao soltar um slider, a leitura é enviada na hora e a mudança aparece no dashboard em tempo real. Ele passa pelo mesmo caminho de uma ESP32 real (`POST /enviar-dados` com `X-API-Key`), então nada no backend ou no frontend sabe que os dados são simulados.

**Recursos:**

- 🏭 **Máquinas vindas da API:** a lista é sincronizada a cada 15 s por `GET /dispositivos/maquinas`, assim como o estado de manutenção (uma ordem aberta com data de hoje ou anterior coloca a máquina em `Manutenção`);
- ⚡ **Potência calculada**, nunca digitada: `P = V × I × FP`, para que o dataset não tenha combinações fisicamente impossíveis;
- 🎲 **Ruído realista** sobre os valores base e **modo automático**, que alterna paradas (`Inativa`/`Desligada`) como no chão de fábrica;
- 💥 **Cenários de falha reproduzíveis**:

| Cenário | Efeito | Duração |
|---|---|---|
| 🔩 Desgaste de rolamento | Vibração sobe aos poucos até 3,5×, corrente +10% | 5 min |
| ⚡ Sobrecarga | Corrente +40%, leve queda de tensão | 30 s |
| 📉 Queda de tensão | Tensão cai para ~190 V, corrente +12% | 45 s |
| 🌀 Desbalanceamento | Vibração oscilante | 2 min |

- 🧪 **Coleta automática** (menu ⋮): dispara falhas sozinha em todas as máquinas, sorteando o **tipo**, a **intensidade** (0,5× a 1,5×) e a **duração** (0,6× a 1,6× da padrão), com 2 a 8 min de operação normal entre uma falha e outra. A variação impede que o modelo só decore a fórmula do simulador;
- 🏷️ **Rótulo verdadeiro para o ML:** cada leitura é gravada em `simulador/dados/rotulos.csv` com o cenário ativo (`normal`, `sobrecarga`, …), a intensidade, o progresso da falha e a sessão de coleta. O rótulo **nunca** vai para a API, pois uma ESP32 real não sabe que está com falha. O CSV pode ser baixado pelo menu do painel;
- ⏸️ **Pausar, retomar e desligar todas** pelo menu ⋮. *Desligar todas* envia uma última leitura `Desligada` de cada máquina antes de pausar, para o dashboard não ficar mostrando a última leitura como atual;
- 📦 **Buffer offline:** se a API cair, as leituras ficam guardadas e são reenviadas em ordem cronológica quando ela volta.

**Executando localmente** (com a API rodando em `http://localhost:8000`):

```bash
pip install -r simulador/requirements.txt
python -m simulador.main
```

Acesse **http://localhost:8081**. O simulador lê o mesmo `.env` da raiz; as variáveis específicas são:

| Variável | Padrão | Descrição |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8000` | Endereço da API |
| `API_KEY` | chave de dev | Deve ser igual à da API |
| `INTERVALO_ENVIO_S` | `2` | Intervalo entre leituras |
| `INICIAR_PAUSADO` | `false` | Com `true`, o simulador sobe com todas as máquinas pausadas, e reinícios ou deploys nunca religam o envio sozinhos |
| `PAINEL_SENHA` | *(vazio)* | Senha do painel. **Defina em produção** |
| `STORAGE_SECRET` | aleatório | Assina o cookie de login (fixe para manter sessões entre restarts) |
| `PORT` | `8081` | Porta do painel (o Railway define sozinho) |

**Deploy no Railway:** crie um serviço a partir deste repositório com a variável `RAILWAY_DOCKERFILE_PATH=simulador/Dockerfile` e configure `API_BASE_URL`, `API_KEY`, `PAINEL_SENHA` e, de preferência, `INICIAR_PAUSADO=true`. Como o disco do Railway é efêmero, baixe o CSV de rótulos antes de um novo deploy.

### 📊 Gerando o dataset de treino

Para treinar os modelos não é preciso deixar o painel rodando por horas. O gerador offline usa **o mesmo motor do painel** (física, cenários e coleta automática) com um relógio simulado: gera dias de operação em segundos, sem API e sem gravar nada no banco.

```bash
python -m simulador.gerar_dataset
```

```
Dataset gerado em 107.7s: ml/dados/dataset.csv
6 sessões × 12 h · 518400 leituras · 764 falhas disparadas
  normal                 467002  (90.1%)
  desgaste_rolamento      30610  (5.9%)
  desbalanceamento        12640  (2.4%)
  queda_tensao             4878  (0.9%)
  sobrecarga               3270  (0.6%)
```

- No gerador, as falhas são **mais raras** (10 a 30 min de operação normal entre elas, ajustável com `--pausa-min` e `--pausa-max`) do que na coleta ao vivo do painel, como numa fábrica real. Falhas frequentes demais "contaminariam" a linha de base de 30 min usada pelo ML;
- Cada **sessão** tem semente própria e fica num dia diferente, para que treino e teste sejam separados por sessão, e não por linhas sorteadas (linhas vizinhas são quase idênticas e vazariam de um lado para o outro);
- A mesma `--seed` sempre gera o mesmo arquivo, então os experimentos são reprodutíveis;
- O CSV tem as mesmas colunas do `rotulos.csv` do painel, e os dois podem ser combinados.

| Coluna | Significado |
|---|---|
| `sessao` | Sessão de coleta (`offline-s42-01`, `coleta-…` ou `manual`) |
| `cenario` | Rótulo verdadeiro: `normal`, `manutencao` ou a falha |
| `intensidade` | Força da falha (0 quando normal) |
| `cenario_progresso` | De 0 a 1, quanto da falha já passou. Serve para medir a antecedência da detecção |
| `parametros_alterados` | 1 se os sliders estavam fora do perfil nominal |
| `tensao_volt` … `frequencia_hz` | Exatamente o que foi (ou seria) enviado à API |

---

## 🧠 Machine Learning

A pasta `ml/` treina os modelos, e a API os aplica a **cada leitura recebida**, gerando alertas em tempo real. O sistema responde três perguntas:

| Pergunta | Técnica | Resultado no teste |
|---|---|---|
| **Detecção:** está fora do padrão? | Isolation Forest, treinada só com operação normal | **99,6%** das falhas detectadas, atraso mediano de **12 s**, **0,66** alarme falso por máquina-dia |
| **Diagnóstico:** que falha é? | Árvore de decisão (profundidade 6) | **98,5%** de acerto no tipo da falha |
| **Prognóstico:** quando passa do limite? | Regressão linear com termo quadrático | Erro médio de **0,4 min** ao prever quando a vibração dobra |

<sub>Avaliado em 2 sessões (261 falhas) que o modelo nunca viu no treino, simulando exatamente as regras do monitor da API.</sub>

<div align="center">
<img src="ml/figuras/03_deteccao.png" alt="Detecção por tipo de falha e alarmes falsos" width="850">
</div>

### Como funciona

1. **Features de janela:** cada leitura vira 15 números calculados sobre os últimos 30 s e 3 min (desvio, ruído e tendência de tensão, corrente, potência, vibração e frequência), sempre **em relação à linha de base da própria máquina** (mediana dos últimos 30 min). Afinal, 5,8 g de vibração é normal numa injetora e alarmante numa prensa;
2. **Detecção:** a Isolation Forest aprende como é o normal e estranha o resto, então também acusa falhas de tipos que nunca viu. Um alerta só é confirmado após **5 leituras seguidas (10 s)**. Comparada com limites fixos por feature (sem ML), detecta o mesmo e reduz os alarmes falsos de **26 para 0,66 por máquina-dia**;
3. **Diagnóstico:** a árvore de decisão é legível. Dá para desenhar as regras e conferir que fazem sentido físico (por exemplo, o que separa uma sobrecarga de uma queda de tensão é a **potência**: sobe na primeira e quase não muda na segunda). O diagnóstico do alerta é um **voto ponderado pela pontuação de anomalia**: o meio da falha pesa muito, e os minutos de transição depois dela pesam pouco. Com voto simples, a sobrecarga acertava só 24%;
4. **Prognóstico:** no desgaste de rolamento, uma regressão sobre os últimos 3 min projeta quando a vibração vai chegar ao **dobro do normal**. O termo quadrático acompanha a aceleração do desgaste, e quando erra, erra para **mais cedo**, que é o lado seguro para agendar a manutenção.

<div align="center">
<img src="ml/figuras/08_prognostico.png" alt="Prognóstico de um desgaste de rolamento" width="850">
</div>

### Executando

```bash
pip install -r ml/requirements.txt
python -m simulador.gerar_dataset   # gera ml/dados/dataset.csv
python -m ml.treinar                # treina, avalia e salva o modelo
```

```
Treinado em 14s → ml/modelos/modelo_falhas.joblib
Detecção:    99.6% das 261 falhas de teste, atraso mediano 12s, 0.66 alarmes falsos por máquina-dia
Diagnóstico: 98.5% de acerto em 260 falhas detectadas
Prognóstico: erro médio de 0.4 min em 122 previsões de desgaste
```

O notebook **[`ml/analise.ipynb`](ml/analise.ipynb)** mostra o raciocínio completo: exploração dos dados, comparação com a linha de base sem ML, o efeito da persistência, a árvore desenhada, as variações da regressão, a antecedência da detecção e as limitações. Os gráficos ficam em `ml/figuras/`, prontos para a apresentação.

| Arquivo | Papel |
|---|---|
| `ml/features.py` | Cálculo das features. **O mesmo código** roda na API, para o modelo ver em produção o que viu no treino |
| `ml/modelo.py` | Detector, diagnóstico e confirmação por persistência |
| `ml/alertas.py` | Regras de abrir, diagnosticar e encerrar alertas, **as mesmas** no monitor da API e na avaliação |
| `ml/tendencia.py` | Regressão do prognóstico |
| `ml/avaliacao.py` | Métricas por ocorrência de falha (não por linha) |
| `ml/treinar.py` | Pipeline de treino reprodutível |
| `ml/modelos/` | Modelo treinado (`.joblib`) e métricas (`metricas.json`) |

### Na API

O monitor (`app/monitor.py`) roda a cada `POST /enviar-dados`, **depois** da resposta à ESP32:

1. Guarda a leitura no histórico da máquina (só com a máquina `Ativa`) e calcula as features;
2. **5 leituras anômalas seguidas (10 s)** abrem um alerta, que nasce como "diagnóstico em andamento";
3. Após mais **5 leituras anômalas**, o diagnóstico aparece, e continua sendo votado enquanto o alerta está aberto. Para o desgaste, a regressão estima quando a vibração chega ao limite;
4. **3 minutos normais** encerram o alerta. Com 1 minuto, o alerta fechava e reabria durante a transição, gerando duplicados.

Cada mudança é gravada na tabela `alertas` e enviada pelo WebSocket `/ws/alertas`.

- **Sem cegueira depois de um deploy:** na inicialização, o monitor recarrega os alertas abertos e os últimos 33 min de leituras de cada máquina. Sem isso, cada máquina precisaria de ~8 min de operação antes de ser avaliada;
- **Isolado da telemetria:** se o modelo não carregar (ou `ML_HABILITADO=false`), o monitor fica desligado e a API segue normal. Um erro no ML nunca afeta a gravação das leituras;
- **Configuração:** `ML_HABILITADO` (padrão `true`) e `ML_MODELO_PATH` (padrão `ml/modelos/modelo_falhas.joblib`). O estado pode ser conferido em `GET /ml/status`.

> **Sobre os números:** os dados vêm do simulador, então as falhas seguem fórmulas que nós escrevemos. Para o resultado não ser só "o modelo decorou a fórmula", cada falha tem intensidade e duração sorteadas, e o teste usa sessões inteiras que o modelo nunca viu. Em dados reais o desempenho esperado é menor; o notebook discute as limitações.

---

## 🧪 Testes e CI

Os testes ficam em `tests/`, divididos em três camadas:

| Camada | Pasta | O que cobre |
|---|---|---|
| 🧩 Unitários | `tests/unit` | Autenticação, modelos, WebSocket manager, repositório com mocks, simulador (física, cenários, buffer e rótulos) ML (features sem vazamento do futuro, regressão e treino completo) e o monitor de alertas, inclusive **de ponta a ponta com o modelo treinado** em cada tipo de falha |
| 🌐 API | `tests/api` | Rotas, login, RBAC, telemetria, alertas e WebSocket |
| 🗄️ Integração | `tests/integration` | Repositório rodando contra um PostgreSQL real |

```bash
pip install -r requirements-dev.txt -r ml/requirements.txt

# Unitários + API, com cobertura
pytest tests/unit tests/api --cov=app --cov=simulador --cov=ml --cov-report=term-missing

# Integração (exige um PostgreSQL com o schema aplicado)
pytest tests/integration
```

A pipeline do **GitHub Actions** (`.github/workflows/pipeline.yml`) roda a cada push e pull request:

1. **Code Quality** — compilação, `ruff check` e `ruff format --check`;
2. **Compatibility** — instalação e importação da aplicação no Ubuntu e no Windows;
3. **Automated Tests** — testes unitários e de API com cobertura;
4. **Integration Tests** — testes contra um serviço PostgreSQL 18 com o schema aplicado.

O Dependabot mantém as dependências atualizadas.

---

## 📁 Estrutura do projeto

```
Simple-IHM-Backend/
├── app/
│   ├── main.py               # Rotas REST e WebSocket
│   ├── auth.py               # JWT, API Key e RBAC
│   ├── models.py             # Schemas Pydantic
│   ├── repository.py         # Consultas SQL (asyncpg)
│   ├── database.py           # Pool de conexões
│   ├── dbconfig.py           # Configuração por variáveis de ambiente
│   ├── websocket_manager.py  # Gerenciador de conexões em tempo real
│   ├── monitor.py            # Monitor de ML: alertas a cada leitura
│   └── migracoes.py          # Aplica database/migrations na inicialização
├── simulador/
│   ├── main.py               # Painel NiceGUI
│   ├── estado.py             # Estado das máquinas e laço de envio
│   ├── fisica.py             # Ruído, potência e cenários de falha
│   ├── cliente_api.py        # HTTP com buffer offline
│   ├── rotulos.py            # CSV com o rótulo verdadeiro (dataset do ML)
│   ├── coleta.py             # Coleta automática de falhas variadas
│   ├── gerar_dataset.py      # Gerador offline do dataset de treino
│   └── Dockerfile
├── ml/
│   ├── features.py           # Features de janela (compartilhadas com a API)
│   ├── modelo.py             # Detector, diagnóstico e persistência
│   ├── tendencia.py          # Regressão do prognóstico
│   ├── alertas.py            # Regras dos alertas (API e avaliação)
│   ├── avaliacao.py          # Métricas por ocorrência de falha
│   ├── treinar.py            # Pipeline de treino
│   ├── analise.ipynb         # Notebook com a análise completa
│   ├── figuras/              # Gráficos para a apresentação
│   └── modelos/              # Modelo treinado e métricas
├── database/
│   ├── schema.sql            # Schema do PostgreSQL
│   └── migrations/           # Migrações aplicadas pela API
├── tests/
│   ├── unit/
│   ├── api/
│   └── integration/
├── docs/images/              # Imagens do README
├── .github/workflows/        # Pipeline de CI
├── Dockerfile
└── docker-compose.yml
```

---

## 👥 Equipe

O projeto foi desenvolvido em equipe, simulando um ambiente real de desenvolvimento de software:

| Área | Responsável |
|---|---|
| ⚙️ **Backend e banco de dados** (este repositório) | [Pedro Cavenaghi](https://github.com/Pedro-Cavenaghi) |
| 🧪 **Testes, Docker e pipeline de CI** (GitHub Actions) | [João Luis](https://github.com/joaoluis2211) |
| 🖥️ **Frontend e dashboard** ([Simple-IHM-Frontend](https://github.com/SamukaSantos-DEV/Simple-IHM-Frontend)) | [Samuka Santos](https://github.com/SamukaSantos-DEV) |
| 📝 **Documentação e apresentação** | João Pedro |

<div align="center">

<br>

<sub>🎓 Projeto acadêmico — Fatec</sub>

</div>
