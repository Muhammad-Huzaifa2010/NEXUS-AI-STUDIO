# NEXUS AI STUDIO

NEXUS AI STUDIO is a multi-agent AI workspace built with React, FastAPI, LangGraph, and Groq. It routes user requests to specialist agents, shares their outputs, and produces one synthesized response.

## Features

- Orchestrator-led routing to Research, Execution, Content, and Deep Analysis agents.
- Sequential specialist execution with shared agent context.
- Source metadata, deduplication, and evidence excerpts from Tavily results.
- Source links in research responses are generated from retrieved results rather than model-written URLs.
- Live Server-Sent Events activity streaming.
- Calculator and unit-conversion tools with a bounded tool registry.
- Optional live web research through Tavily.
- Optional PostgreSQL task history.
- React workspace for task execution, activity monitoring, and history.
- Docker Compose deployment for PostgreSQL, backend, and frontend.

## Architecture

```text
React workspace
      |
      | HTTP / Server-Sent Events
      v
Nginx reverse proxy
      |
      v
FastAPI
      |
      v
LangGraph workflow
      |
      +--> Orchestrator
      +--> Research Agent
      +--> Execution Agent
      +--> Content Agent
      +--> Deep Analysis Agent
      |
      v
Finalizer / synthesized response
```

Task execution, database persistence, and external provider calls are separated into API routes, workflow nodes, services, tools, schemas, and database helpers.

### Agent responsibilities

- **Orchestrator:** Builds a specialist task plan and selects the next approved agent.
- **Research Agent:** Uses Tavily when configured and returns normalized sources with metadata and excerpts.
- **Execution Agent:** Runs approved calculator and unit-conversion tools.
- **Content Agent:** Creates written explanations, summaries, and reports.
- **Deep Analysis Agent:** Performs critical analysis using the shared structured evidence.
- **Finalizer:** Synthesizes specialist outputs and appends the retrieved source links.

## Technology stack

- Frontend: React 19, Vite, JavaScript
- Backend: Python 3.13, FastAPI, Pydantic
- AI orchestration: LangGraph
- LLM provider: Groq
- Optional web research: Tavily
- Database: PostgreSQL 16, asyncpg
- Deployment: Docker Compose and Nginx

## Project structure

```text
NEXUS-AI-STUDIO/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── tools/
│   │   └── workflows/
│   └── tests/
├── frontend/
│   ├── deploy/
│   ├── public/
│   └── src/
├── docker-compose.yml
├── Dockerfile.backend
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.13
- Node.js 22 or later
- npm
- A Groq API key
- Docker and Docker Compose for container deployment
- PostgreSQL optional for local development

## Environment configuration

Copy the root template for Docker Compose:

```bash
cp .env.example .env
chmod 600 .env
```

| Variable | Required | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | Docker and LLM tasks | Authenticates Groq API requests |
| `GROQ_MODEL` | No | Groq model name; defaults to `openai/gpt-oss-20b` |
| `TAVILY_API_KEY` | No | Enables Tavily live web research; empty disables it |
| `RESEARCH_SEARCH_BUDGET` | No | Maximum complementary searches per research task (1-8; defaults to 5) |
| `RESEARCH_RESULTS_PER_QUERY` | No | Maximum Tavily results per query (1-10; defaults to 5) |
| `RESEARCH_MAX_SOURCES` | No | Maximum unique sources passed to agents (1-10; defaults to 6) |
| `POSTGRES_DB` | Docker | PostgreSQL database name |
| `POSTGRES_USER` | Docker | PostgreSQL application user |
| `POSTGRES_PASSWORD` | Docker | PostgreSQL application password |
| `APP_BIND` | Docker | Host interface used by the frontend |
| `APP_PORT` | Docker | Host port used by the frontend |
| `PUBLIC_URL` | Docker | Public frontend origin reported to the backend |

Use placeholder values in `.env.example`. Never commit real credentials.

For backend-only local development:

```bash
cd backend
cp .env.example .env
```

The backend template uses `GROQ_API_KEY`, `GROQ_MODEL`, `TAVILY_API_KEY`, `DATABASE_URL`, and `FRONTEND_URL`.
Research uses a bounded query budget and deduplicates results before passing evidence to agents.

## Local development

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set `DATABASE_URL` to enable PostgreSQL task history. Without it, the API continues to run and history persistence is disabled.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

The Vite server proxies `/api` requests to `http://127.0.0.1:8000`.

## Docker deployment

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 backend
```

The default frontend binding is `127.0.0.1:8080`. The backend is internal to the Compose network; PostgreSQL is also reachable from the host at `127.0.0.1:5435` for local development. Stop the stack without deleting database data:

```bash
docker compose down
```

To also delete the PostgreSQL volume:

```bash
docker compose down -v
```

That command permanently deletes task-history data.

## Database

PostgreSQL task history is optional. When enabled, FastAPI creates the `task_history` table if it does not exist and stores:

- Request text
- Status
- Workflow
- Selected agent
- Final response
- Tool events
- Activity events
- Creation timestamp

## API

### Health

```http
GET /api/health
```

### Execute a task

```http
POST /api/tasks/run
Content-Type: application/json

{"request":"Research PostgreSQL and summarize its main use cases."}
```

### Stream a task

```http
POST /api/tasks/stream
Accept: text/event-stream
Content-Type: application/json

{"request":"Calculate the area of a 12 meter square."}
```

The stream emits `status`, `activity`, `result`, and `error` Server-Sent Events. Research tasks include a source list built from retrieved Tavily URLs. Source categories are publisher-origin hints, not independent verification of a source's accuracy.

### Task history

```http
GET /api/tasks/history?limit=50
GET /api/tasks/history/{task_id}
```

FastAPI API documentation is available at `/docs` on the backend in local development.

## Testing

Backend:

```bash
cd backend
python -m compileall -q app tests
python -m unittest discover -s tests -v
```

Research-service and workflow tests use mocked responses and do not require API keys.

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Docker Compose:

```bash
docker compose config -q
```

## Security considerations

- Keep `.env` files out of source control.
- Restrict root `.env` permissions on shared hosts.
- Rotate any API key or database password that may have been exposed.
- The application intentionally has no user accounts, registration, login, or authentication.
- Internet-facing deployments should use TLS, rate limiting, monitoring, backups, and secret rotation; apply access controls at the hosting layer if needed.
- The Nginx configuration provides proxying and security headers; no application login is provided.
- Research inputs and retrieved webpage content should be treated as untrusted data.

## Troubleshooting

- **AI tasks return 503:** configure `GROQ_API_KEY`.
- **Task history is unavailable:** set `DATABASE_URL` locally or verify the Compose database service.
- **Frontend cannot reach the backend:** verify proxy configuration and backend health.
- **Docker startup fails:** confirm `.env` contains the required Groq key and database password.
- **Tavily research is skipped:** set `TAVILY_API_KEY` or continue with model knowledge.
- **Research sources are insufficient:** check backend search diagnostics and adjust the bounded `RESEARCH_*` limits if appropriate.

## Current limitations

- The application is account-free; task history is shared by this deployment and is not filtered by user accounts.
- Tavily is optional and Groq usage depends on provider configuration and quota.
- Source categories are simple domain-based hints, not reliability judgments. Retrieved sources are not independently validated.
- PostgreSQL history stores the final report and activity records; raw source excerpts are not persisted separately.
- PostgreSQL stores task history; it is not persistent vector memory or a RAG system.
- Tool support is currently limited to approved calculator and unit-conversion operations.
- Live web research is available only when Tavily is configured.
