# NEXUS AI STUDIO — deployment status

This document records the current project capabilities and validation status.

## Added in this package

- Docker Compose services for PostgreSQL, FastAPI backend, and Nginx frontend.
- Optional production overlay with Caddy-managed HTTPS.
- Nginx Basic Authentication and API request rate limiting.
- PostgreSQL task-history persistence and history API endpoints.
- Task History screen in the existing React interface.
- Persistent named volumes for PostgreSQL data and generated video/artifact storage.
- Linux `espeak-ng` narration fallback, FFmpeg, ffprobe, and DejaVu fonts in the backend image.
- Portable storage-path configuration for containers.
- Updated deployment and recovery instructions.

## Verification performed in this environment

- `python -m compileall -q app tests` from `backend/` — passed.
- `python -m unittest discover -s tests -v` from `backend/` — 29 tests passed.
- `docker compose config -q` — passed.
- `npm run build` from `frontend/` — passed.
- `npm run lint` — passed.

## Verification not performed here

- Docker image builds and container startup: Docker Engine is not running in this environment.
- End-to-end PostgreSQL connection and task persistence: no PostgreSQL service is available in this environment.
- Real MP4 rendering inside Docker: FFmpeg is present in the environment, but `espeak-ng` is not installed here. The backend Dockerfile installs it.
- Live Groq agent run: requires the user's private API key and quota.

## Important product scope

This is a Dockerized deployment baseline, not a fully finished multi-user SaaS. The five existing agents and sequential orchestration are retained. The six proposed workflow categories are not yet six separate workflow engines. The login is shared HTTP Basic Authentication; a public multi-user service needs individual accounts and authorization.
