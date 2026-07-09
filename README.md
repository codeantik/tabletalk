# Table Talk

Chat-based multi-CSV data analysis PoC. Upload a set of CSVs, ask questions in
natural language, get back text / chart / table answers. See the full
architecture decisions and phase plan in the project brief (not included in
this repo).

**Status:** Phase 2 complete — CSV ingestion (Phase 1) plus a single-turn
NL→SQL query endpoint. The chat UI and multi-turn conversation land in
later phases.

## Phase 1: sessions & CSV ingestion

- `POST /api/sessions` — creates a session (a fresh in-memory DuckDB
  connection) and returns `{session_id, created_at, expires_at}`.
- `POST /api/sessions/{session_id}/upload` — multipart upload of one or more
  `.csv` files. Validation (extension, size limit, parseability) runs for the
  whole batch before anything is written, so a bad file can't leave the
  session half-updated. Column names and the table name (from the filename)
  are normalized to `lower_snake_case` identifiers; re-uploading the same
  filename replaces its table in place, and name collisions within one batch
  get a numeric suffix.
- `GET /api/sessions/{session_id}/tables` — lists every table currently
  loaded in the session, with DuckDB-inferred column types and row counts.
- `DELETE /api/sessions/{session_id}` — explicitly closes a session.

Sessions idle for longer than `SESSION_TTL_MINUTES` are evicted lazily (on
the next call into the session manager) rather than by a background timer —
sufficient for a request-driven PoC, but a session won't be freed purely by
the clock ticking if nothing else touches the manager.

## Phase 2: NL→SQL queries

- `POST /api/sessions/{session_id}/query` — body `{"question": "..."}`.
  The question, plus the session's table/column schema, is sent to the LLM
  (function-calling, forced tool call) to produce `{sql, explanation}`.
  Always returns `200`; the response body is
  `{session_id, sql, columns, rows, explanation, error, row_limit_applied}`,
  with `error` set (and `columns`/`rows`/`explanation` left `null`) instead
  of an HTTP error status when the query couldn't be answered.
- **SQL safety**: every generated query is parsed with `sqlglot` before it
  ever reaches DuckDB. Only a single, read-only `SELECT` (CTEs allowed) that
  references tables already loaded into the session is permitted — no
  `INSERT`/`UPDATE`/`DELETE`/`DROP`/multi-statement payloads, and no tables
  from other sessions.
- **One self-correcting retry**: if the first attempt fails validation, the
  rejected SQL and the specific error are fed back to the LLM for a single
  retry before giving up and returning the error contract.
- **Row limiting**: `LIMIT` is injected (if absent) or capped (if too high)
  to `MAX_ROWS_RETURNED` directly in the executed SQL, so the `sql` field in
  the response always matches what actually ran; `row_limit_applied`
  indicates whether that happened.
- **Query timeout**: execution runs in a worker thread bounded by
  `QUERY_TIMEOUT_SECONDS`; a query that runs long is interrupted and comes
  back as an `error`, not a hung request.

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
  minimal boilerplate for the query and chat endpoints.
- **DuckDB** — queries CSVs directly via `read_csv_auto` with full SQL,
  in-process and per-session; avoids a pandas-agent's code-execution surface
  and SQLite's manual schema/typing setup.
- **sqlglot** — parses and validates LLM-generated SQL before execution: a
  single read-only `SELECT` over known tables, or the query is rejected
  (Phase 2).
- **pydantic-settings** — typed config loaded from `.env`.
- **Next.js (App Router) + TypeScript** — chat UI, file upload, charts.
- **OpenAI API** — NL→SQL generation via function calling for structured
  `{sql, explanation}` output (Phase 2); NL response synthesis for the chat
  UI comes in a later phase.

## Known limitations (Phase 2)

- Sessions live in backend process memory only — a restart drops all
  uploaded data, and there's no multi-worker/horizontal-scaling support.
- TTL eviction is lazy (swept on next session-manager call), not proactive.
- `/query` is single-turn only — no conversation history or follow-up
  questions that reference a prior answer, and only one self-correcting
  retry on validation failure before surfacing an error.
- No chat UI yet — that's a later phase.
- Docker path is unverified in this environment (see note above).
