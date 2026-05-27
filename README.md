# Airport Search

An end-to-end airport search engine, powered by Postgres.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/installation) + Node.js

## Running locally

### 1. Start Postgres

```bash
docker compose up -d
```

### 2. Start the backend

```bash
cd apps/backend
uv sync
uv run uvicorn main:app --reload
```

API runs at http://localhost:8000. Tables are created automatically on first startup.

### 3. Apply search indexes

Run once after the backend has started (so the `airports` table exists):

```bash
docker compose exec -T postgres psql -U postgres -d myapp < apps/backend/migrations/001_setup_search.sql
```

### 4. Start the frontend

In a new terminal, from the repo root:

```bash
pnpm install
cd apps/web && pnpm dev
```

Frontend runs at http://localhost:5173.

## Environment

The backend reads `apps/backend/.env`. The default values match the Docker Compose service:

```env
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/myapp
OPENAI_API_KEY=           # required for the /ingest enrichment endpoint
```
