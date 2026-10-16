# Simple IHM - API de Telemetria Industrial (Backend)

🚀 **Link da API em Produção:** [Acesse aqui no Railway]( https://simple-ihm-api-production.up.railway.app/docs )

O **Simple IHM** é um ecossistema IoT projetado para monitoramento de telemetria de máquinas industriais em tempo real. O objetivo principal do projeto é aplicar os conceitos de **Manutenção Preditiva e Corretiva** em um ambiente de chão de fábrica, traduzindo dados complexos de sensores em uma interface visual simples, direta e de baixa carga cognitiva para os operadores.

Este repositório contém estritamente a **Central Backend** do ecossistema, responsável pela recepção concorrente de dados, validação estrita e persistência analítica. O Frontend em React foi desenvolvido em paralelo e integrado através do consumo desta API.

---

## 🛠️ Tecnologias Utilizadas

*   **Linguagem:** Python 3.13+
*   **Framework Web:** FastAPI (Arquitetura assíncrona)
*   **Banco de Dados:** PostgreSQL (Modelo Relacional de Alta Performance)
*   **Validação de Dados:** Pydantic
*   **ORM / Query Builder:** SQLAlchemy / Asyncpg
*   **Ambiente de Nuvem:** Railway

---

## 📐 Diferenciais de Arquitetura e Engenharia de Software

O backend foi projetado para suportar o fluxo contínuo de dados gerados por microcontroladores (ESP32) simulando o chão de fábrica a cada 2 segundos. Para garantir a estabilidade, foram aplicados os seguintes padrões:

1.  **Desempenho Assíncrono Nativo (`async/await`):** Utilização do motor assíncrono do FastAPI sobre Uvicorn para gerenciar múltiplas requisições concorrentes dos sensores sem bloqueio de threads ou travamento do servidor.
2.  **Validação na Porta de Entrada (Pydantic):** Garantia de integridade dos dados coletados no hardware. Qualquer leitura mal formatada é rejeitada antes de atingir o banco de dados.
3.  **Persistência Otmizada com Séries Temporais:** Modelagem do PostgreSQL focada em logs históricos (`logs_maquinas`). Implementação de operações atômicas de *Upsert* (`ON CONFLICT`) para atualizar estados em tempo real e registrar o histórico com baixa latência, poupando recursos de CPU.
4.  **Integridade Relacional Estrita:** Uso rigoroso de restrições de banco (Constraints, Primary Keys e Foreign Keys com `ON DELETE CASCADE`) para impedir dados órfãos e garantir consistência absoluta.

---

## 🛣️ Principais Endpoints da API

*   `POST /maquinas` - Cadastro de novos ativos industriais (Tags, Setor, Nome).
*   `GET /maquinas` - Listagem e status em tempo real de todas as máquinas da planta.
*   `POST /telemetria` - Endpoint de alta frequência consumido pelo hardware para envio de Corrente (A) e Vibração (RMS).
*   `GET /telemetria/historico/{maquina_id}` - Retorna a série temporal de dados para plotagem de gráficos analíticos de manutenção preditiva.

*(A documentação interativa completa e gerada automaticamente pode ser acessada via:
https://simple-ihm-api-production.up.railway.app/docs )*

---

## 👥 Desenvolvimento e Divisão do Projeto

O projeto foi construído em equipe, simulando o ambiente real de desenvolvimento de software:
*   **Backend & Banco de Dados (Este repositório):** Desenvolvido por [Pedro Henrique Cavenaghi](https://github.com/Pedro-Cavenaghi), com foco em engenharia de dados, regras de negócio e infraestrutura assíncrona.
*   **Frontend & Dashboard (React):** Desenvolvido em repositório paralelo, focado na experiência do usuário (UX) industrial e renderização dos gráficos em tempo real.

---
*Projeto acadêmico*
