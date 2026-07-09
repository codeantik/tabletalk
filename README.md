# Table Talk

Chat-based multi-CSV data analysis PoC. Upload a set of CSVs, ask questions in
natural language, get back text / chart / table answers. See the full
architecture decisions and phase plan in the project brief (not included in
this repo).

**Status:** Phase 5 complete — CSV ingestion (Phase 1), NL→SQL generation
(Phase 2), deterministic text/chart/table response composition (Phase 3), a
stateful multi-turn chat endpoint with rate limiting and structured error
handling (Phase 4), and a Next.js chat UI with upload, charts, and tables
(Phase 5).

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

> The endpoint described in this section (`POST /.../query`) was replaced in
> Phase 4 by the stateful `POST /.../messages` endpoint — see below. The SQL
> generation/validation/retry logic described here is unchanged; only the
> route and response envelope moved.

- The question, plus the session's table/column schema, is sent to the LLM
  (function-calling, forced tool call) to produce `{sql, explanation}`.
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

The unified response shape introduced here — `{session_id, sql_used, intent,
text, chart, table, error, row_limit_applied}` — is what Phase 4's
`POST /.../messages` returns (with `question`/`created_at` added). `intent`
and `chart`/`table` replaced Phase 2's raw `columns`/`rows`/`explanation`
fields as a breaking change to that contract, not an additive one.

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

## Phase 4: chat API & multi-turn conversation

- `POST /api/sessions/{session_id}/messages` — body `{"question": "..."}`.
  This **replaces** Phase 2/3's `POST /.../query`; it wires the same SQL
  generation/validation/execution/composition pipeline behind a stateful
  endpoint. Response shape: `{session_id, question, created_at, sql_used,
  intent, text, chart, table, error, row_limit_applied}`.
- `GET /api/sessions/{session_id}/messages` — returns
  `{session_id, messages: [...]}`, every turn asked in the session so far
  (each shaped like the `POST` response above), for frontend reload/refresh.
- **Conversation store** (`app/services/conversation_store.py`): each
  session's `SessionRecord` carries a `turns: list[ConversationTurn]`. A
  turn stores the question plus the already-shaped answer (sql/intent/text/
  chart/table/error) — not a raw, unbounded DuckDB result set. Chart/table
  payloads are already row-limited and shaped for the client (Phase 3), so
  this is still "light" relative to the query's real intermediate result,
  while being enough to replay history on page reload without re-running
  every query.
- **Follow-up resolution**: before generating SQL, `query_engine.run_nl_query`
  pulls the last `HISTORY_TURNS_CONTEXT` (default 3) turns via
  `conversation_store.recent_turns` and passes only their lightweight
  `{question, sql, intent}` into `llm_client.generate_sql`'s prompt (not the
  full stored answer, to keep the prompt small). The system prompt instructs
  the model to treat the most recent turn's SQL as a base to modify when the
  question is a follow-up ("break that down by category", "just the top 3"),
  and to ignore the history when the question is unrelated to it.
- **Rate limiting** (`app/services/rate_limiter.py`): a simple in-memory
  token bucket per session (`RATE_LIMIT_CAPACITY` burst,
  `RATE_LIMIT_REFILL_PER_MINUTE` sustained rate). Exceeding it returns
  `429`. State is process-local, like `session_manager`'s connections — a
  production deployment running multiple backend workers would need a
  shared store (Redis) instead.
- **Structured logging** (`app/core/logging.py`): every turn — success or
  failure — logs one line (`question`, `sql`, `intent`, `validation` result,
  `execution` result, `error`, `latency_ms`) via the stdlib `logging` module
  instead of `print`. This was originally a Phase 2 requirement that hadn't
  actually been implemented; it's added here since Phase 4's error-handling
  work touches the same code paths, and Phase 8's evaluation write-up
  depends on these logs existing.
- **Error-handling matrix** — two deliberately different tiers, continuing
  the precedent set in Phase 2/3 rather than moving every failure to an HTTP
  status code:

  | Failure                                              | Response |
  |-------------------------------------------------------|----------|
  | Unsupported question, SQL validation failure (after retry), execution timeout, malformed model output | `200` + `error` field set (chat-level: the user asked something, got a graceful "couldn't answer") |
  | Unknown/expired session                                | `404` |
  | Upload validation failure (bad file, too large, etc.)  | `400` with `{message, errors: [...]}` |
  | Rate limit exceeded                                    | `429` |
  | LLM API itself unreachable/timed out (`LLMServiceError`, both the SQL-generation and summary-synthesis calls) | `502` for SQL generation (no answer is possible at all); the summary call instead **degrades gracefully** to a deterministic caption (e.g. "The query returned 3 row(s). (AI summary is temporarily unavailable.)") since the SQL already executed successfully by that point |
  | Any other unhandled exception                          | `500` with a generic message; the real exception is logged server-side, never sent to the client |

  Chat-level failures are chosen over HTTP-level ones specifically so the
  frontend can render them as an inline assistant message in the chat
  thread, not a toast/error page — consistent with how Phase 2/3 already
  treated "couldn't answer this question" as part of the conversation, not
  a request failure.

## Phase 5: frontend (upload, chat, visualization)

A single-page Next.js (App Router) client app — no server-side rendering of
session data, since everything is per-browser session state.

- **Session bootstrap** (`app/page.tsx`): on load, a stored `session_id` is
  read from `localStorage`; if present, `GET /tables` and `GET /messages` are
  used to rehydrate loaded tables and chat history. If it's missing or the
  backend 404s (expired/evicted session), a new session is created via
  `POST /api/sessions` and stored instead — this is what makes a page refresh
  preserve history without a login system.
- **Upload** (`components/FileUpload.tsx`): drag-drop or file picker, with
  client-side `.csv`-extension and size-limit checks before the request is
  even sent. On success, renders per-file confirmation (source filename →
  normalized table name, row count, column count). There is **no
  missing-value/outlier report in this UI** — Phase 1 was deliberately scoped
  down to column-name normalization only (see Phase 1 section above), so the
  upload response has nothing beyond row counts and column types to show.
- **Chat** (`components/ChatPanel.tsx`, `ChatMessage.tsx`): question/answer
  bubbles, a disabled input+send button while a request is pending or before
  any file is uploaded, and inline error bubbles for backend failures
  (couldn't-answer, rate-limited, LLM-service-down) instead of a toast or
  crash — consistent with the chat-level error contract from Phase 2–4.
- **Response rendering** (`ChartView.tsx`, `TableView.tsx`, `SqlDisclosure.tsx`):
  switches on the response's `chart`/`table`/`text` fields (the backend has
  already decided the shape per Phase 3 — the frontend never re-decides
  text-vs-chart-vs-table). Charts use Recharts (`chart:line` → `LineChart`,
  `chart:bar` → `BarChart`, `chart:pie` → `PieChart`); every response with a
  `sql_used` value gets a collapsible "Show query" disclosure for
  transparency.
- **Tables sidebar** (`TablesSidebar.tsx`): lists every table currently
  loaded in the session (name, source filename, row count, columns) so the
  user can see what's actually queryable.

**Bugs found and fixed during Phase 5 end-to-end testing** (with a real
OpenAI key, not just the placeholder-key error path — these are backend
fixes, surfaced only once the frontend made full round-trips possible):

- **Trend queries always failed.** CSV date columns are never coerced to a
  native `DATE` type (Phase 1's scoped-down cleaning), so DuckDB stores them
  as `VARCHAR`; the LLM generated `STRFTIME(order_date, '%Y-%m')` assuming a
  date type, which DuckDB rejects at execution time with no VARCHAR
  overload. Fixed with one added rule in `llm_client.py`'s system prompt:
  cast a VARCHAR column to `DATE` before using it in a date function.
- **Trend results rendered as a table, not a line chart.** Even after the
  fix above, grouping by `STRFTIME(...)` naturally produces a formatted
  string column (e.g. `"2024-01"`), not a native `date`/`datetime` value —
  and `response_composer._is_datelike` only recognized the latter, so the
  result was classified as `category` and fell back to a table. Fixed by
  teaching `_is_datelike` to also recognize ISO-date-shaped strings
  (`YYYY-MM` / `YYYY-MM-DD`), since the composer's job is to classify the
  *actual* result shape, not assume a particular SQL style.
- **Any result containing a date/Decimal value crashed the whole request.**
  `llm_client.synthesize_summary` passed raw DuckDB row values straight into
  `json.dumps`, which can't serialize `date`/`datetime`/`Decimal` — an
  unhandled `TypeError` on the first query that returned one (which the
  first bug above had been silently preventing until it was fixed). Fixed
  with `json.dumps(..., default=str)`.
- **Pie chart slices had no visible labels.** `ChartView.tsx`'s `Pie` used a
  `label` render function that returned a bare string; Recharts needs a
  `<text>` element from a custom label renderer, so nothing appeared except
  on hover. Replaced with a `<Legend>` (also added to multi-series line/bar
  charts, where the same color-to-name ambiguity applies).

## Project structure

```
/backend        FastAPI app (routes in app/api, config/session mgmt in
                 app/core, business logic in app/services, schemas in
                 app/models)
/frontend       Next.js + TypeScript app (App Router): app/page.tsx wires
                 session bootstrap + layout; components/ holds upload, chat,
                 and response-rendering UI; lib/api.ts + lib/storage.ts hold
                 the typed backend client and localStorage session helpers
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
Visit `http://localhost:3000` — upload CSVs in the sidebar, then ask
questions in the chat panel. A session is created automatically on first
load and persisted in `localStorage` across refreshes.

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
limits, query/LLM timeouts, multi-turn history depth, rate limiting, CORS
origin, frontend API URL).

## Libraries used & why (so far)

- **FastAPI** — async-friendly, typed request/response models via Pydantic,
  minimal boilerplate for the chat endpoint and its exception handlers.
- **DuckDB** — queries CSVs directly via `read_csv_auto` with full SQL,
  in-process and per-session; avoids a pandas-agent's code-execution surface
  and SQLite's manual schema/typing setup.
- **sqlglot** — parses and validates LLM-generated SQL before execution: a
  single read-only `SELECT` over known tables, or the query is rejected
  (Phase 2).
- **pydantic-settings** — typed config loaded from `.env`.
- **Next.js (App Router) + TypeScript** — chat UI, file upload, session
  state; all client components (no server-rendered session data).
- **Recharts** — `LineChart`/`BarChart`/`PieChart` bound directly to the
  backend's `{x, series: [{name, value}]}` chart JSON contract (Phase 3),
  with no reshaping needed on the frontend.
- **OpenAI API** — NL→SQL generation plus intent classification via function
  calling for structured `{sql, explanation, intent}` output (Phase 2/3),
  now with conversation history for follow-up resolution (Phase 4), and a
  second call for result-aware NL summaries (Phase 3).

## Known limitations (Phase 5)

- Sessions live in backend process memory only — a restart drops all
  uploaded data and conversation history, and there's no multi-worker/
  horizontal-scaling support (session affinity or a shared store would be
  needed for that).
- TTL eviction is lazy (swept on next session-manager call), not proactive.
- Follow-up resolution is a single LLM prompt-context trick (last 3 turns'
  question/sql/intent) — there's no explicit slot-filling or clarification
  loop, so a genuinely ambiguous follow-up gets the model's best guess
  rather than a clarifying question back to the user.
- Rate limiting is a per-process in-memory token bucket — fine for a PoC
  single-worker deployment, not multi-worker-safe (would need Redis).
- Response composition only handles a single category/date column plus one
  or more numeric columns per chart; multi-dimension breakdowns (e.g.
  category × subcategory) fall back to a table rather than a grouped/stacked
  chart.
- The result-aware summary call sends at most 30 result rows to the LLM; for
  larger result sets the summary is grounded in a sample, not the full set
  (noted explicitly in the prompt sent to the model).
- Docker path is unverified in this environment (see note above).
- **Session identity is a `localStorage` key, not auth.** A different
  browser/device (or a cleared `localStorage`) always starts a fresh
  session; there's no way to resume a session from another machine.
- **The upload UI shows only row counts and columns, no data-quality
  report.** Phase 1 was scoped down to column-name normalization only (no
  missing-value counts or outlier flags are computed server-side), so
  there's nothing richer for the frontend to render.
- **An LLM-service-down error (502) is shown once but never persisted** —
  by the Phase 4 design, `run_nl_query` only records a turn when there's
  something (even a graceful failure) to store; a 502 means no answer
  exists at all, so a page refresh after one won't show that failed
  question in history. Chat-level errors (couldn't-answer, validation
  failure, timeout) *are* persisted and survive a refresh.
- Chart rendering assumes the single category/date + numeric-series shapes
  Phase 3 produces; it doesn't need to handle anything wider since the
  backend never emits a shape outside that contract.
