# AGENTS.md

## Project Overview

Full-stack web app with a React frontend, FastAPI backend, and PostgreSQL database
running in Docker. All services are orchestrated via Docker Compose.

---

## Repo Structure

```
.
├── apps/web/               # React app (Vite + TypeScript)
├── apps/backend/           # FastAPI app (Python 3.12)
├── docker-compose.yml
└── AGENTS.md
```

---

## Services

| Service  | Tech              | Port | Container name |
| -------- | ----------------- | ---- | -------------- |
| Frontend | React + Vite + TS | 5173 | fe             |
| Backend  | FastAPI + Uvicorn | 8000 | be             |
| Database | PostgreSQL 16     | 5432 | db             |

---

## Running the Stack

```bash
docker compose up --build          # Start all services
docker compose down -v             # Stop + wipe volumes
docker compose logs -f be          # Tail backend logs
```

Frontend dev server (outside Docker):

```bash
cd frontend && npm install && npm run dev
```

Backend dev server (outside Docker):

```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

## Frontend Conventions (React)

- **Framework:** React 18 + Vite + TypeScript (strict mode)
- **Styling:** Tailwind CSS — no inline styles, no CSS modules
- **State:** Zustand for global state; React Query for server state
- **Routing:** React Router v6 — file-based layout under `src/pages/`
- **API calls:** Always go through `src/api/client.ts` (Axios instance)
- **Component rules:**
  - Functional components only, no class components
  - One component per file; filename matches component name
  - Props interfaces named `<ComponentName>Props`
- **Testing:** Vitest + React Testing Library; run with `npm test`
- **Linting:** ESLint + Prettier — run `npm run lint` before committing

---

## Backend Conventions (FastAPI)

- **Python version:** 3.12
- **Package manager:** pip + `requirements.txt` (pin all versions)
- **Project layout:**
  ```
  backend/app/
  ├── main.py          # App factory, router registration
  ├── api/             # Route handlers (one file per domain)
  ├── models/          # SQLAlchemy ORM models
  ├── schemas/         # Pydantic request/response schemas
  ├── services/        # Business logic (no DB calls here)
  ├── db/              # Session, engine, base
  └── core/            # Config, settings (pydantic-settings)
  ```
- **Naming:**
  - Routes: `snake_case`; HTTP verbs explicit (`get_user`, `create_order`)
  - Models: `PascalCase`; table names `plural_snake_case`
  - Schemas: suffix with `Create`, `Update`, `Read` (e.g. `UserRead`)
- **DB access:** Always use the injected `AsyncSession` — no sync DB calls
- **Error handling:** Raise `HTTPException`; never let raw exceptions bubble up
- **Testing:** Pytest + HTTPX async client; run with `pytest`
- **Env vars:** Loaded via `app/core/config.py` using `pydantic-settings`; never hardcode secrets

---

## Database Conventions (PostgreSQL)

- **ORM:** SQLAlchemy 2.x (async) + Alembic for migrations
- **Migrations:**
  ```bash
  # Inside the backend container or venv:
  alembic revision --autogenerate -m "describe change"
  alembic upgrade head
  ```
- **Rules:**
  - Every table must have a `UUID` primary key and `created_at` / `updated_at` timestamps
  - Foreign keys must have explicit `ON DELETE` behavior
  - Never DROP columns in a single migration — deprecate, then remove
  - All migrations must be reversible (implement `downgrade()`)
- **Seeding:** `db/seed.sql` is run automatically on first container start

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

| Variable       | Service  | Description                     |
| -------------- | -------- | ------------------------------- |
| `DATABASE_URL` | backend  | Async postgres DSN              |
| `SECRET_KEY`   | backend  | JWT signing key                 |
| `CORS_ORIGINS` | backend  | Comma-separated allowed origins |
| `VITE_API_URL` | frontend | Backend base URL for Axios      |

---

## Agent Guidelines

- **Before making changes:** Read the relevant layer's conventions above.
- **Adding a feature:** Create schema → model (+ migration) → service → route → frontend API call → UI component, in that order.
- **Never** edit generated migration files after they've been committed.
- **Never** add business logic directly inside route handlers — use `services/`.
- **Never** import backend modules into frontend code or vice versa.
- **Always** run `npm run lint` (frontend) and `pytest` (backend) after changes.
- **Always** update or add tests when touching existing logic.
- **Prefer** small, focused PRs over large sweeping changes.
- When in doubt about architecture, ask rather than assume.
