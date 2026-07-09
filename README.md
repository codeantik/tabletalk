# Table Talk

Chat-based multi-CSV data analysis PoC. Upload a set of CSVs, ask questions in
natural language, get back text / chart / table answers. See the full
architecture decisions and phase plan in the project brief (not included in
this repo).

**Status:** Phase 3 complete — CSV ingestion (Phase 1), a single-turn NL→SQL
query endpoint (Phase 2), and deterministic response composition into
text/chart/table (Phase 3). The chat UI and multi-turn conversation land in
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

## Phase 3: response composition (text / chart / table)

`POST /api/sessions/{session_id}/query` now returns a unified response
shape: `{session_id, sql_used, intent, text, chart, table, error,
row_limit_applied}`. `intent` and `chart`/`table` replace Phase 2's raw
`columns`/`rows`/`explanation` fields — this is a breaking change to the
Phase 2 contract, not an additive one.

- **Intent classification** is produced by the same LLM call that generates
  the SQL (`generate_sql_query` tool call gains an `intent` field: `trend`,
  `comparison`, `single_value`, `lookup`, `distribution`, or `unsupported`).
  No separate classification call.
- **Deterministic text/chart/table mapping** (`app/services/response_composer.py`)
  combines `intent` with the *actual* shape of the executed result — not the
  LLM's word alone — so a mismatched intent still degrades to a sane
  response instead of a bad chart:

  | Result shape                                            | Intent                  | Response type |
  |----------------------------------------------------------|--------------------------|----------------|
  | 0 rows, or 1 row × 1 column                               | any                      | `text`         |
  | 1 date column + ≥1 numeric column, >1 row                 | `trend`                  | `chart:line`   |
  | 1 category column + 1 numeric column, 2–6 rows             | `distribution`           | `chart:pie`    |
  | 1 category column + ≥1 numeric column, 2–50 rows           | `comparison`/`distribution` | `chart:bar` |
  | anything else (including intent/shape mismatches)          | `lookup` / fallback      | `table`        |

  Pie charts are used sparingly (≤6 categories, `distribution` intent only,
  single metric); wider category counts fall back to a bar chart, and
  anything beyond `BAR_MAX_CATEGORIES` (50) falls back to a table.
- **Chart JSON contract**: `{type, data: [{x, series: [{name, value}]}]}` —
  a shaped, minimal structure for the frontend charting library, not a raw
  DataFrame dump.
- **Result-aware NL summary**: after execution, a second LLM call
  (`synthesize_summary`) is given the actual result rows (capped at 30 rows
  to bound tokens) and produces a 1–3 sentence `text` summary grounded in
  real values — distinct from Phase 2's `explanation`, which only describes
  the query and runs before results exist. `text` is populated for every
  successful response, including chart responses: charts always ship with a
  caption (the "mix" default), never chart-only.
- **`intent: unsupported` handling**: if the model determines a question
  can't be answered from the uploaded data (off-topic, needs a write, needs
  outside knowledge), SQL generation/validation/execution is skipped
  entirely and the model's explanation is surfaced via the existing `error`
  field — consistent with Phase 2's "couldn't answer → `error` field, still
  a 200" contract, rather than a new response path.

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
- **OpenAI API** — NL→SQL generation plus intent classification via function
  calling for structured `{sql, explanation, intent}` output (Phase 2/3),
  and a second call for result-aware NL summaries (Phase 3).

## Known limitations (Phase 3)

- Sessions live in backend process memory only — a restart drops all
  uploaded data, and there's no multi-worker/horizontal-scaling support.
- TTL eviction is lazy (swept on next session-manager call), not proactive.
- `/query` is single-turn only — no conversation history or follow-up
  questions that reference a prior answer, and only one self-correcting
  retry on validation failure before surfacing an error.
- Response composition only handles a single category/date column plus one
  or more numeric columns per chart; multi-dimension breakdowns (e.g.
  category × subcategory) fall back to a table rather than a grouped/stacked
  chart.
- The result-aware summary call sends at most 30 result rows to the LLM; for
  larger result sets the summary is grounded in a sample, not the full set
  (noted explicitly in the prompt sent to the model).
- No chat UI yet — that's a later phase.
- Docker path is unverified in this environment (see note above).
