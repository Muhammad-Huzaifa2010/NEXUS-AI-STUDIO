# NEXUS AI STUDIO

NEXUS AI STUDIO is a multi-agent AI workspace with a React frontend and a FastAPI/LangGraph backend. The current implementation includes an Orchestrator, Research Agent, Execution Agent, Content Agent, and Video Production Agent.

## Included capabilities

- Bounded orchestration across up to four approved specialist agents.
- Sequential agent execution with shared specialist context and final synthesis.
- Approved calculator and unit-conversion tools; no arbitrary shell execution.
- Live task activity through Server-Sent Events.
- Narrated five-minute MP4 slideshow generation with Pillow and FFmpeg.
- macOS Speech (`say`) on macOS and `espeak-ng` in Linux containers.
- Optional PostgreSQL task history, including request, result, agent plan, activity, tool events, and video references.
- Docker Compose deployment with PostgreSQL, backend, Nginx frontend, persistent volumes, health checks, and HTTP Basic Authentication.

## Quick deployment with Docker

### 1. Prerequisites

- Docker Engine and the Docker Compose plugin (or Docker Desktop on macOS).
- A Groq API key.

### 2. Configure secrets

From the project root:

```bash
cp .env.example .env
```

Edit `.env`, then restrict its permissions with `chmod 600 .env`, and set:

- `GROQ_API_KEY`: your private Groq API key.
- `POSTGRES_PASSWORD`: a long random password containing letters and numbers only.
- `NEXUS_BASIC_AUTH_USER`: the username for the protected web interface.
- `NEXUS_BASIC_AUTH_PASSWORD`: a unique password of at least 16 characters.

Generate random secrets on macOS/Linux if needed:

```bash
openssl rand -hex 24
```

Use different values for the database password and web password. Never commit `.env` or share it in screenshots or ZIP files.

### 3. Build and start the stack

```bash
docker compose up --build -d
```

Open `http://localhost:8080` and sign in with the Basic Authentication username/password from `.env`.

### 4. Verify services

```bash
docker compose ps
docker compose logs --tail=100 backend
curl -I http://localhost:8080/healthz
```

The backend health endpoint is available internally at `/api/health`. It reports Groq, FFmpeg, speech engine, and PostgreSQL readiness. The frontend is published on `127.0.0.1` by default; the database and backend are not published directly to the host.

### 5. Stop or update

```bash
# Stop containers; preserve database and video volumes
docker compose down

# Rebuild after source changes
docker compose up --build -d

# Follow logs
docker compose logs -f backend frontend db
```

To remove containers and persistent data, use `docker compose down -v`. **This permanently deletes the PostgreSQL database and generated videos.** Do not run it unless you intentionally want to erase that data.

## Deploying on a Linux VPS with HTTPS

The production overlay adds Caddy, which obtains and renews HTTPS certificates automatically. Before starting it:

1. Point your domain's DNS A/AAAA record to the VPS.
2. Allow inbound TCP ports 80 and 443 (and UDP 443 for HTTP/3) in the VPS firewall.
3. In `.env`, set `DOMAIN=your-real-domain.example` and `PUBLIC_URL=https://your-real-domain.example`.
4. Keep `APP_BIND=127.0.0.1`; the public entry point is Caddy, not the direct frontend port.

Start the HTTPS deployment:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Caddy forwards HTTPS traffic to the protected Nginx frontend. Keep `.env` readable only by the deployment account. Back up `postgres_data`, `nexus_storage`, and Caddy's `caddy_data` volume before upgrades.

For Render, Railway, or another managed host, use its Docker deployment option and persistent-volume/networking requirements; do not assume this VPS overlay applies unchanged.

## Local development (without Docker)

The existing macOS workflow remains supported. It uses the `backend/.env` file and macOS `say` for narration.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
# Add GROQ_API_KEY to backend/.env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite development server proxies `/api` requests to `http://127.0.0.1:8000`. PostgreSQL persistence is optional in local development; set `DATABASE_URL` if you want task history enabled locally.

## API endpoints

- `GET /api/health`
- `POST /api/tasks/run`
- `POST /api/tasks/stream` (SSE)
- `GET /api/tasks/history?limit=50`
- `GET /api/tasks/history/{task_id}`
- `GET /api/videos/{filename}`
- `GET /docs` (FastAPI API documentation; backend internal in Compose)

## Tests and build checks

```bash
cd backend
source venv/bin/activate
python -m compileall -q app tests
python -m unittest discover -s tests -v

cd ../frontend
npm ci
npm run build
```

The unit tests validate the approved tools and workflow-routing helpers. They do not replace an end-to-end test using a real Groq key, PostgreSQL, FFmpeg, and speech engine.

## Current scope and limitations

- Video output is a narrated scene-card slideshow encoded as MP4, not a fully animated cinematic video.
- The specialist agents use the configured Groq model; this project does not provide a model or API quota.
- PostgreSQL stores completed/failed task history. It is not a general document memory or vector database.
- The frontend uses HTTP Basic Authentication at the Nginx entry point in the Compose deployment. For a multi-user public product, replace this shared login with individual accounts, role-based authorization, per-user quotas, and audit controls.
- A public deployment still needs a real domain, correct DNS/firewall settings, backups, monitoring, and provider-specific configuration. The included Caddy overlay handles HTTPS certificate provisioning when those prerequisites are met.
- The six workflow categories shown/planned in the product concept are not all implemented as separate dedicated workflow engines in this source snapshot; the current Orchestrator chooses among the available specialist agents.
