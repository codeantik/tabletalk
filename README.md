# Table Talk

Chat-based multi-CSV data analysis PoC. Upload a set of CSVs, ask questions in
natural language, get back text / chart / table answers. See the full
architecture decisions and phase plan in the project brief (not included in
this repo).

**Status:** Phase 0 complete — empty-but-correct skeleton, health-check
round trip verified end to end. Feature work (upload, NL→SQL, chat) lands in
later phases.

## Project structure

```
/backend        FastAPI app (routes in app/api, config/session mgmt in
                 app/core, business logic in app/services, schemas in
                 app/models)
/frontend       Next.js + TypeScript app (App Router)
docker-compose.yml
.env.example
```

## Setup & Run — local dev

Requires Python 3.11+ and Node 20+.

**Backend:**
```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy ..\.env.example ..\.env  # fill in OPENAI_API_KEY etc.
uvicorn app.main:app --reload --port 8000
```
Health check: `GET http://localhost:8000/api/health` → `{"status": "ok"}`

**Frontend:**
```
cd frontend
npm install
copy .env.local.example .env.local   # or create with NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
Visit `http://localhost:3000` — the page shows a live "Backend connected"
status pulled from `/api/health`.

## Setup & Run — Docker

```
docker compose up --build
```
Then visit `http://localhost:3000` (frontend) and `http://localhost:8000/api/health`
(backend). Requires a filled-in `.env` at the repo root.

> **Note:** Docker is not installed in the environment this project was
> scaffolded in, so the Docker path is written to match the local-dev setup
> exactly (same env vars, same ports) but has not been run end-to-end here.
> The local dev commands above are the verified path.

## Environment variables

See `.env.example` for the full list (LLM provider/key, session TTL, upload
limits, query timeout, CORS origin, frontend API URL).

## Libraries used & why (so far)

- **FastAPI** — async-friendly, typed request/response models via Pydantic,
  minimal boilerplate for the SQL-generation and chat endpoints coming in
  later phases.
- **DuckDB** — queries CSVs directly via `read_csv_auto` with full SQL,
  in-process and per-session; avoids a pandas-agent's code-execution surface
  and SQLite's manual schema/typing setup.
- **sqlglot** — parses and validates LLM-generated SQL before execution
  (Phase 2).
- **pydantic-settings** — typed config loaded from `.env`.
- **Next.js (App Router) + TypeScript** — chat UI, file upload, charts.
- **OpenAI API** — NL→SQL generation and NL response synthesis, via
  function calling for structured `{sql, intent, explanation}` output.

## Known limitations (Phase 0)

- No feature logic yet — this is scaffolding only.
- Docker path is unverified in this environment (see note above).
