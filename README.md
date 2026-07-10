# Table Talk

Chat-based multi-CSV data analysis PoC. Upload a set of CSVs, ask questions
in natural language, get back text / chart / table answers, with real
multi-turn follow-ups.

**Status:** feature-complete — ingestion, validated NL→SQL, deterministic
text/chart/table composition, a stateful multi-turn chat API, a Next.js UI,
a hardening pass (large files, concurrency, prompt-injection, edge cases),
and Docker configs (reviewed, not run end-to-end — see
[Known limitations](#known-limitations)).

## Problem Statement

Build a proof-of-concept where a user uploads multiple related CSVs — a
normalized e-commerce schema (`customers`, `orders`, `order_items`,
`products`, `payment`, `shipments`, `reviews`, `suppliers`, joined via
`customer_id` / `order_id` / `product_id` / `supplier_id`) — and asks
questions in plain English through a chat interface. The system must turn
each question into a correct, safe query, decide whether the answer reads
best as text, a chart, or a table, and support natural follow-ups ("now
break it down by category") — without letting the model execute arbitrary
code or touch data outside the current session.

## Architecture Overview

```
Browser (Next.js)
   |  multipart CSV upload
   v
POST /api/sessions/{id}/upload --> csv_ingestion.py --> per-session DuckDB
                                                          (in-memory, one
                                                           connection + lock)
                                                                |
                                                                v
                                            schema card (tables / columns /
                                            types / sample rows / join keys)

Browser -- "question" --> POST /api/sessions/{id}/messages
                                    |
                                    v
                        query_engine.run_nl_query
                                    |
                    +---------------+----------------+
                    v                                 v
        llm_client.generate_sql              conversation_store
        (schema card + question +            (last N turns as
         history --> {sql, intent})           follow-up context)
                    |
                    v
        sqlglot validation gate
        (SELECT/WITH only, known tables,
         LIMIT injected or capped)
                    |
              pass -+- fail --> one bounded retry --> graceful error
                    v
        DuckDB execution (timeout-bounded, session-locked)
                    |
                    v
        response_composer (intent + actual result shape -->
        text / chart:line / chart:bar / chart:pie / table)
                    |
                    v
        llm_client.synthesize_summary (result rows --> grounded caption)
                    |
                    v
        unified response {text, chart?, table?, sql_used, intent}
```

Non-negotiable invariants: the **LLM never executes code** — it only ever
produces a SQL string + `intent`, parsed/validated by `sqlglot` before
DuckDB sees it. The **backend decides text vs. chart vs. table**
deterministically from `(intent, actual result shape)`, not the model's own
words. **Sessions are isolated** — one in-memory DuckDB connection per
upload, keyed by `session_id`, locked against same-session concurrent
requests. **Conversation history is explicit structured context**
(`{question, sql, intent}` for the last few turns), not a raw transcript.

## How it works — a worked example

> **"What's total revenue by product category?"**

1. `run_nl_query` pulls the session's schema card + empty history, calls
   `generate_sql`, gets back a forced tool call: `{sql: "SELECT p.category,
   SUM(...) AS revenue FROM order_items oi JOIN products p ON ... GROUP BY
   p.category ORDER BY revenue DESC", intent: "comparison"}`.
2. `sqlglot` validates it (single `SELECT`, known tables, no forbidden
   keywords) and injects a `LIMIT` since none was given.
3. DuckDB executes it under the session lock, bounded by
   `QUERY_TIMEOUT_SECONDS`, returning ~8 rows.
4. `response_composer` sees 1 category column + 1 numeric column across 8
   rows and picks `chart:bar`, shaping it into `{type, data: [{x, series}]}`.
5. `synthesize_summary` is given the *actual* result rows (not asked to
   re-derive numbers) and returns: "Electronics leads with $482K in
   revenue, followed by Home & Kitchen at $310K."
6. The turn (`{question, sql, intent}`) is stored. A follow-up — **"Now
   just show me the top 3"** — feeds that context back into the next
   `generate_sql` call, which modifies the previous query
   (`ORDER BY revenue DESC LIMIT 3`) instead of starting fresh.

## Data cleaning

Applied per-column, after the column-name normalization above, in
`app/services/data_cleaning.py` — deliberately conservative, since this is a
data-*analysis* tool and silently altering ground truth would undermine the
one thing it's supposed to get right:

- **Missing values.** Common null-like sentinels (`N/A`, `null`, `-`, `""`,
  `unknown`, ...) are normalized to real `NULL` so `COUNT`/`AVG`/`GROUP BY`
  don't treat them as their own bogus category.
- **Data types.** An object column is coerced to numeric or date **only** if
  ≥95% of its non-null values parse successfully (with a minimum sample size
  of 20, so a tiny column can't hit that bar by chance) — e.g. `"$1,200.00"`
  strings become real numbers. Cells that fail to parse become `NULL` (never
  a dropped row), counted in the missing-value report. This threshold, not
  100%, is deliberate: real CSVs almost always have a stray dirty cell even
  in a fundamentally numeric column, and requiring perfection would mean the
  fix rarely fires; a lower bar risks miscoercing genuinely mixed columns
  (e.g. alphanumeric IDs).
- **Outliers.** Counted per numeric column via IQR (1.5×) and reported —
  **never removed or altered**. Silently discarding a real answer (e.g. the
  largest order) would be worse than leaving it in.

The full report (`missing_count`, `missing_pct`, `outlier_count`,
`coerced_from`) is computed once at ingest time and returned on every table
in `UploadResponse`/`TablesResponse`, surfaced in the upload sidebar.

This only applies on the pandas ingestion path (files below
`LARGE_FILE_THRESHOLD_MB`). Large files loaded via native `read_csv_auto`
skip the pandas-side coercion (same performance tradeoff as column-name
cleaning — see below) and rely on DuckDB's own type sniffing instead; the
missing-value and outlier report is still computed for them via SQL against
the loaded table, it just reports sentinel strings as missing rather than
having mutated them to `NULL` in place.

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
copy .env.local.example .env.local   # or NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
Visit `http://localhost:3000`. A session is created automatically on first
load and persisted in `localStorage` across refreshes.

**Backend tests:** `cd backend && .venv\Scripts\activate && pytest`

**Manual testing:** [`tests.md`](tests.md) is a step-by-step walkthrough for
exercising every core feature by hand — ingestion/data-quality reporting,
NL→SQL generation, the bounded validation-*and*-execution retry, chart/table/
text response composition, multi-turn follow-ups, and the Phase 6 edge-case
checklist — using the sample CSVs in `data/`. Run it after the automated
suite, since the automated suite catches regressions but not LLM output
quality or cross-service UI wiring.

## Setup & Run — Docker

```
docker compose up --build
```
Visit `http://localhost:3000` (frontend) / `http://localhost:8000/api/health`
(backend). Requires a filled-in `.env` at the repo root.

> Docker isn't installed in this environment, so this path is statically
> reviewed and bug-fixed (missing `.dockerignore`s, pinned single worker —
> see [Known limitations](#known-limitations)) but not run end-to-end.
> Local dev above is the verified path.

## Environment variables

See `.env.example` for the full list (LLM provider/key, session TTL, upload
limits, query/LLM timeouts, multi-turn history depth, rate limiting, CORS
origin, frontend API URL).

## Libraries used & why

- **FastAPI** — async, typed request/response models, minimal boilerplate.
- **DuckDB** — queries CSVs directly via `read_csv_auto` with full SQL,
  in-process per session; avoids a pandas-agent's code-execution surface
  and SQLite's manual schema setup.
- **sqlglot** — parses/validates LLM-generated SQL before execution.
- **pydantic-settings** — typed config from `.env`.
- **Next.js (App Router) + TypeScript** — chat UI, upload, session state;
  all client components.
- **Tailwind CSS + shadcn/ui (Base UI)** — themeable design tokens for the
  chat/upload/response UI, no per-component hardcoded styles.
- **Recharts** — bound directly to the backend's `{x, series}` chart JSON,
  no client-side reshaping.
- **@react-three/fiber (Three.js)** — the ambient schema-graph visualization
  in the empty/upload state; lazy-loaded, degrades to a static SVG under
  `prefers-reduced-motion`.
- **OpenAI API** — NL→SQL + intent classification via function calling, plus
  a second call for result-aware NL summaries.

## Evaluation Strategy

Documentation, not implementation — how the system's outputs would be
validated on an ongoing basis.

**1. Accuracy of AI-generated insights.** Two failure modes need separate
checks: wrong **SQL** (bad join/aggregation/hallucinated column) vs. a
**summary** that misdescribes a correct result.
- *Golden query set*: ~30–50 `(question, expected result)` pairs covering
  every table/join. Comparison is against **result values**, not SQL text
  (different SQL can be equally correct) — run the real pipeline, diff rows.
- *LLM-as-judge*: a second LLM call scores whether every factual claim in
  the generated summary is supported by the result rows (binary
  grounded/not, not a vague quality score) — catches hallucinated summaries
  that a correct-SQL check would miss.
- *Human spot-checks*: structured per-turn logs (`question`, `sql`,
  `intent`, `error`, `latency_ms`) already exist; sample real traffic
  weekly, stratified to include every error, as the backstop for blind
  spots the automated checks share.

**2. Performance on large datasets.** Already measured (see table below) via
`backend/scripts/perf_load_test.py`, which tiles real `order_items.csv` rows
(not synthetic generation, to keep join selectivity/skew representative) up
to 5M rows. A production rollout would track p50/p95 latency continuously
and DuckDB session memory (scales with concurrent sessions × loaded-table
size — capacity planning is single-machine-bounded today, see limitations).

**3. Edge cases & robustness.** The table below is backed by one pytest per
row (`backend/tests/test_edge_cases.py`), part of a 101-test suite that
already covers ingestion, data cleaning, query engine, response composition, conversation
store, concurrency, rate limiting, and the sessions API. **Missing: CI
wiring** — no `.github/workflows/` exists, so the suite runs locally, not on
push/PR. Adversarial testing (chat-input prompt injection, data-embedded
injection via CSV cell content) is already exercised manually and traced —
see [Prompt-injection review](#notable-bugs-found--fixed) below; a CI
version would replay a fixed list of known injection phrasings.

### Performance (large-file ingestion)

| Rows | File size | pandas → DuckDB | native `read_csv_auto` | Query latency |
|-----:|----------:|-----------------:|------------------------:|---------------:|
| 20,000 | 0.5 MB | ~0.05s | ~0.1s (fixed overhead dominates) | <0.01s |
| 1,000,000 | 25 MB | ~0.8s | ~0.3s (~2.5x faster) | <0.01s |
| 5,000,000 | 129 MB | ~4.5s | ~1.3s (~3.5x faster) | ~0.03s |

Files above `LARGE_FILE_THRESHOLD_MB` (default 20MB) skip the pandas
profiling pass and load straight via `read_csv_auto`, then apply the same
column-naming rules after the fact.

### Edge cases

| Scenario | Handling |
|---|---|
| Empty result set | Composed as `text` ("no results"), never an empty chart/table |
| Nonexistent column reference | Passes `sqlglot` (table-name-only check); fails at DuckDB execution; caught as a chat-level `error`, not a 500 |
| Ambiguous question | No clarification loop (PoC limitation) — model's best guess is used, verified not to crash |
| Non-English input | Question is an opaque string end-to-end, no ASCII assumption |
| Overly broad question | Row limit applies regardless of how wide the generated SQL is |
| Sentiment / free-text understanding | Out of scope by design — `intent: unsupported`, not approximated with a keyword hack |

## Notable bugs found & fixed

Found during hardening/end-to-end testing, not part of the original design:

- **Trend queries failed / rendered as tables.** CSV dates are stored as
  `VARCHAR` (Phase-1 cleaning is column-name-normalization only), so
  `STRFTIME` calls on them failed, and even after casting, the resulting
  formatted string wasn't recognized as date-like. Fixed by instructing the
  model to cast to `DATE` first, and teaching the composer to recognize
  ISO-date-shaped strings.
- **Any date/Decimal result crashed the request.** `synthesize_summary`
  passed raw DuckDB values into `json.dumps`, which can't serialize
  `date`/`Decimal`. Fixed with `json.dumps(..., default=str)`.
- **DuckDB concurrency hazard.** Two threads calling `.execute()` on the
  same session's connection with no lock produced **silently wrong results,
  or occasionally crashed the process** (Windows heap corruption). Fixed
  with a `threading.Lock` per session, scoped tightly around each DB call
  (not held across LLM network calls).
- **Prompt-injection review (data-embedded).** The only LLM call that ever
  sees row content is `synthesize_summary`; its output never flows back
  into a later prompt (history only carries `{question, sql, intent}`), so
  a malicious CSV cell can skew a summary's wording at most — never reach
  SQL generation or execution. Added defense-in-depth instructions anyway.
- **Missing `.dockerignore`s.** The frontend Dockerfile's `COPY . .` would
  have pulled the host's `node_modules` (platform-specific native binaries)
  into the Linux image. Added `.dockerignore` to both services; pinned
  `--workers 1` explicitly since session state lives in process memory.
- **Pie chart slices had no labels; pandas parse crashed on ragged/mixed
  CSVs** — both caught in ingestion/response-rendering tests and fixed.

## Known limitations

- Sessions live in backend process memory — a restart drops all data; no
  multi-worker/horizontal-scaling support without session affinity or a
  shared store (TTL eviction is also lazy, swept on next access).
- Follow-up resolution is a prompt-context trick (last 3 turns), not
  explicit slot-filling — an ambiguous follow-up gets a best guess.
- Rate limiting is an in-memory token bucket — not multi-worker-safe.
- Sentiment/free-text-understanding questions are explicitly out of scope.
- Large-file path measured to 5M rows/129MB; `MAX_UPLOAD_SIZE_MB` (default
  50MB) would need raising to accept a file that large end-to-end.
- Charts handle one category/date column + numeric series only; wider
  breakdowns fall back to a table. Summaries sample ≤30 rows for larger sets.
- Docker path is unverified end-to-end in this environment.
- Session identity is a `localStorage` key, not auth — no cross-device
  session resume.
- Type coercion (see [Data cleaning](#data-cleaning)) only runs on the
  pandas ingestion path; large files loaded via native `read_csv_auto` get a
  missing/outlier report but not the coercion pass itself.
- No CI wiring yet — the pytest suite (101 tests) runs locally, not gated.

## Bonus features implemented

- **Multi-turn conversation** — follow-ups resolve against the previous turn's `{question, sql, intent}`, not a fresh context-free query.
- **Efficient large-CSV handling** — files above the size threshold load via
  native `read_csv_auto`, ~2.5–3.5x faster than the pandas path at scale.
- **Dockerization** — `docker compose up --build`; reviewed and bug-fixed,
  not yet run end-to-end in this environment.
- **Themed, subject-grounded UI** — Tailwind/shadcn design system, an ambient
  Three.js schema-graph visualization, dark mode, full responsiveness.

## Project structure

```
/backend        FastAPI app (routes in app/api, config/session mgmt in
                 app/core, business logic in app/services, schemas in
                 app/models); scripts/ holds manual load-test and
                 concurrency-hazard demos (not part of the pytest suite)
/frontend       Next.js + TypeScript app (App Router): app/page.tsx wires
                 session bootstrap + layout; components/ holds upload, chat,
                 and response-rendering UI; lib/api.ts + lib/storage.ts hold
                 the typed backend client and localStorage session helpers
docker-compose.yml
.env.example
```
