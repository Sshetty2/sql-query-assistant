# go-service

Full-feature Go reimplementation of the SQL Query Assistant API. Endpoint-equivalent to the Python `server.py` and ready to take over from it. See `PARITY.md` for the full feature matrix and `POST_MVP.md` for the small set of remaining items.

**Endpoints:**
- `GET /` — health check
- `GET /databases` — list demo databases
- `GET /databases/{db_id}/schema` — introspect a database
- `POST /query` — sync natural-language query
- `POST /query/stream` — SSE-streamed query execution
- `POST /query/patch` — interactive plan modification (add/remove columns, change ORDER BY, adjust LIMIT)
- `POST /query/chat` — agentic chat with `run_query` and `respond` tools (respond takes optional `revised_sql` + `explanation` for inline SQL revisions)
- `POST /query/chat/reset` — clear chat session
- `POST /query/execute-sql` — direct SELECT execution
- `POST /cancel` — cancel an in-flight workflow

**Workflow nodes:**
13 main-pipeline nodes + 3 data-analysis nodes + 1 patch transformation node + 1 optional FK inference node.

**LLM providers:**
- OpenAI (chat / structured output via `json_schema` / embeddings / streaming / tool calling)
- Anthropic (chat / structured output via forced tool-use / streaming / native tool calling)
- Ollama (chat / structured output via JSON mode; tools are intentionally unsupported)

**Pluggable model routing:**
Same `MODEL_REGISTRY` aliases as Python. Stage-specific overrides via `LOCAL_MODEL_*` / `REMOTE_MODEL_*` env vars.

**SQL generation:**
Hand-rolled deterministic emitter covering selections, joins (inner/left/right/full), filters (=, !=, <, >, IN, NOT IN, BETWEEN, LIKE, starts_with, ends_with, IS NULL, IS NOT NULL), aggregates (COUNT, COUNT_DISTINCT, SUM, AVG, MIN, MAX), GROUP BY, HAVING, ORDER BY, TOP/LIMIT, **window functions** (ROW_NUMBER, RANK, DENSE_RANK, NTILE, LAG, LEAD, windowed aggregates), **subquery filters** (IN/NOT IN/EXISTS/NOT EXISTS), and **dual dialect** emission (T-SQL + SQLite).

## Architecture

```
cmd/server/                # entry — wires logger, gin, env
internal/
├── server/                # gin handlers + SSE: /query, /query/stream, /query/patch,
│                          # /query/chat, /query/chat/reset, /query/execute-sql, /cancel
├── agent/
│   ├── graph.go           # hand-rolled state machine (RunQuery, RunPatch)
│   ├── state.go           # workflow State
│   └── nodes/             # 18 workflow nodes
├── chat/                  # agentic chat: sessions, tools, loop
├── llm/                   # OpenAI + Anthropic + Ollama clients, stage routing
├── sql/                   # T-SQL + SQLite emitter with dialect interface
├── schema/                # SQLite/SQL Server introspection
├── vector/                # in-memory cosine-sim store
├── fk/                    # FK pattern detection + vector matching
├── cancel/                # per-session cancellation registry
├── db/                    # connection management + demo registry
├── thread/                # thread_states.json store
├── models/                # PlannerOutput, DataSummary, ModificationOptions, PatchOperation
└── logger/                # structured logging with request-scoped fields
```

## Build & run

```bash
# Local
cd go-service
go build -o sql-go-service.exe ./cmd/server
USE_TEST_DB=true PORT=8001 ./sql-go-service.exe

# Direct
USE_TEST_DB=true PORT=8001 go run ./cmd/server

# Docker (distroless, ~30 MB)
docker build -t sql-go-service .
docker run --rm -p 8001:8001 \
  -e USE_TEST_DB=true \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd)/../databases:/app/databases:ro \
  sql-go-service
```

## Frontend

The Vite dev server proxies `/api/*` to `http://localhost:8001` by default (see `demo_frontend/vite.config.ts`). Override with `VITE_API_URL=http://localhost:8000 npm run dev` to hit the Python service instead.

## Test

```bash
# Unit + structural tests only (~50 ms)
go test -short ./...

# Including live LLM/SQLite e2e tests (needs ../.env with API keys)
go test ./...

# Opt-in Ollama live test (cold model load can use 10+ GB RAM)
OLLAMA_TEST=true go test ./internal/llm/... -run TestOllama_Live -v
```

128 tests across 31 test files. See `TEST_COVERAGE.md` for the comparison against the Python project's test suite.

## Parity check against Python

Both services running side-by-side:

```bash
# Terminal 1 — Python
USE_TEST_DB=true uvicorn server:app --port 8000 --log-level warning

# Terminal 2 — Go
USE_TEST_DB=true PORT=8001 ./go-service/sql-go-service.exe

# Terminal 3 — diff
./go-service/scripts/parity_check.sh
```

Replays `scripts/parity_prompts.txt` against both services and diffs the SSE event sequence and final SQL/row counts.

## Configuration (env vars)

Same names as the Python service:

| Var | Used for |
|---|---|
| `OPENAI_API_KEY` | Embeddings (always) + chat if a GPT model is configured |
| `ANTHROPIC_API_KEY` | Chat when a Claude model is configured |
| `USE_TEST_DB` | `true` → SQLite demo databases; `false` → SQL Server |
| `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | SQL Server connection (when `USE_TEST_DB=false`) |
| `USE_LOCAL_LLM` | `true` → route all chat through Ollama |
| `OLLAMA_BASE_URL` | Ollama server URL (default `http://localhost:11434`) |
| `REMOTE_LLM_PROVIDER` | `openai`, `anthropic`, or `auto` (default `openai`) |
| `REMOTE_MODEL_STRATEGY`, `REMOTE_MODEL_PLANNING`, `REMOTE_MODEL_FILTERING`, `REMOTE_MODEL_ERROR_CORRECTION`, `REMOTE_MODEL_REFINEMENT`, `REMOTE_MODEL_CHAT` | Per-stage remote model |
| `LOCAL_MODEL_STRATEGY`, `LOCAL_MODEL_PLANNING`, `LOCAL_MODEL_FILTERING`, `LOCAL_MODEL_ERROR_CORRECTION`, `LOCAL_MODEL_REFINEMENT`, `LOCAL_MODEL_CHAT` | Per-stage local model |
| `EMBEDDING_MODEL` | OpenAI embedding model (default `text-embedding-3-small`) |
| `TOP_MOST_RELEVANT_TABLES` | Vector-search top-K (default 10) |
| `INFER_FOREIGN_KEYS` | `true` to enable inference node |
| `FK_INFERENCE_CONFIDENCE_THRESHOLD` | Minimum cosine similarity to accept (default 0.6) |
| `FK_INFERENCE_TOP_K` | Candidates per ID column (default 3) |
| `MAX_CHAT_TOOL_CALLS` | Per-session tool budget (default 3) |
| `LOG_LEVEL` | `debug` / `info` / `warn` / `error` (default `info`) |
| `LOG_FORMAT` | `json` (default) or `text` |
| `PORT` | HTTP port (default 8001) |
