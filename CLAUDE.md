# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Dual-Implementation Project — Read This First

This repository contains **TWO parallel implementations** of the same service. They share the same demo databases, `.env`, `thread_states.json`, frontend, and React UI, and they expose identical HTTP+SSE contracts. The frontend can target either backend by switching one env var.

| Implementation | Location | Stack |
|---|---|---|
| **Python (original)** | `agent/`, `models/`, `database/`, `utils/`, `server.py` | FastAPI + LangGraph + LangChain + SQLGlot + Chroma |
| **Go (rewrite)** | `go-service/` (everything in `cmd/` and `internal/`) | gin + hand-rolled state machine + hand-rolled T-SQL emitter + pure-Go cosine vector store + `microsoft/go-mssqldb` / `modernc.org/sqlite` + official OpenAI/Anthropic/Ollama SDKs |

Both serve the React frontend in `demo_frontend/`. Endpoint shapes and SSE event vocabularies are intentionally identical — see `go-service/PARITY.md` for the full matrix.

### **Parity rule: any new feature ships in BOTH services**

When adding new functionality, you MUST make the change in both Python and Go. This is non-negotiable — the rewrite was done specifically so we can switch backends, and that only stays true if both services keep evolving together.

**What counts as "major" (parity required):**
- New HTTP endpoints or changes to existing ones
- New workflow nodes or changes to node behavior
- Changes to `PlannerOutput`, `DataSummary`, `ModificationOptions`, or any wire model
- New SQL emitter features (window functions, dialects, etc.)
- New LLM provider integrations
- New SSE event types or shape changes to existing events
- Changes to the patch operations or the chat tool surface
- Authentication / authorization changes

**What's OK to do in one place only:**
- Implementation-specific refactors that don't change behavior
- Bug fixes for issues only one implementation has
- Test additions that mirror existing coverage
- Documentation that's specific to one stack's quirks

**Workflow when adding a feature:**
1. Implement and test in one implementation (usually whichever is easier given context)
2. Port to the other (use the existing implementation as the spec)
3. Add equivalent tests in both
4. Update `go-service/PARITY.md` if a previously-unequal feature is now matched
5. Update `go-service/POST_MVP.md` if you're checking a deferred item off the list

The Go service is the source-of-truth-equivalent now — not a prototype. Drift between the two should be treated as a bug.

See **[go-service/README.md](go-service/README.md)**, **[go-service/PARITY.md](go-service/PARITY.md)**, and **[go-service/POST_MVP.md](go-service/POST_MVP.md)** for the Go-side details.

## Project Overview

This is a **SQL Query Assistant** that converts natural language queries into SQL and executes them against a SQL Server database. It uses **LangGraph** for workflow orchestration, **LangChain** with **OpenAI/Anthropic/Ollama** for query planning, **SQLGlot** for deterministic SQL generation, and provides both a **Streamlit UI** and **FastAPI** backend.

The Go reimplementation in `go-service/` is feature-equivalent (see [Dual Implementation](#-dual-implementation-project--read-this-first) above).

### Key Features

- **Deterministic SQL Generation**: SQLGlot-based join synthesizer (no LLM for SQL, zero cost)
- **Two-Stage Planning Architecture**: Text-based strategy generation followed by structured JSON planning
  - **Pre-Planner**: Creates high-level text strategy with domain understanding
  - **Planner**: Converts strategy to structured JSON (PlannerOutput)
  - **Strategy-First Error Correction**: Feedback loops regenerate strategy, not JSON patches
- **3-Stage Schema Filtering**: Vector search + LLM reasoning + FK expansion reduces context to relevant tables only
- **Foreign Key Inference**: Automatic FK discovery for databases without explicit constraints
  - **Standalone FK Agent**: Interactive CLI tool (`fk_inferencing_agent/`) with human-in-the-loop validation
  - **Integrated Inference**: Optional automatic FK inference during query execution (`INFER_FOREIGN_KEYS=true`)
  - **Smart FK Resolution**: Intelligent column name matching for tables without explicit PKs
- **Plan Patching**: Interactive query modification with immediate re-execution
  - **Add/Remove Columns**: Toggle columns on/off without rewriting query
  - **Modify ORDER BY**: Change sorting column and direction
  - **Adjust LIMIT**: Row count slider (10-2000)
  - **Instant Updates**: Deterministic patching with <2s re-execution (no LLM calls)
- **Planner Complexity Tiers**: Three levels optimized for different model sizes (minimal/standard/full)
- **Plan Auditing**: Deterministic validation catches and fixes common mistakes
- **Smart Error Handling**: Feedback-based error correction with iteration limits
  - Error feedback routes back to pre-planner for strategy regeneration
  - Refinement feedback for empty results
  - Separate iteration counters (error: 3, refinement: 3)
- **ORDER BY/LIMIT Support**: Planner generates ordering from requests like "last 10 logins"
- **SQL Server Safety**: Automatic identifier quoting for reserved keywords
- **Query History**: Recent queries sidebar in Streamlit UI (each query is independent, not conversational)

## Environment Setup

Required environment variables (see `.env` file):

### LLM Provider Configuration
- `USE_LOCAL_LLM` - Set to `true` to use local Ollama, `false` for remote providers (default: `false`)
- `REMOTE_LLM_PROVIDER` - Remote provider selection (default: `openai`, only used when `USE_LOCAL_LLM=false`)
  - `openai` - Use OpenAI for all models
  - `anthropic` - Use Anthropic for all models
  - `auto` - Auto-detect provider from model name (allows mixing providers per stage)
- `OPENAI_API_KEY` - OpenAI API key (required when using OpenAI models)
- `ANTHROPIC_API_KEY` - Anthropic API key (required when using Anthropic models)
- `OLLAMA_BASE_URL` - Ollama server URL (default: `http://localhost:11434`, only used when `USE_LOCAL_LLM=true`)

### Model Selection
- `AI_MODEL` - Primary model for query planning
  - When using OpenAI: `gpt-4o-mini`, `gpt-4o`, etc.
  - When using Anthropic: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, etc.
  - When using Ollama: `qwen3:8b`, `llama3`, `mistral`, etc.
- Stage-Specific Model Configuration (optional):
  - `REMOTE_MODEL_STRATEGY` - Pre-planner strategy generation (remote)
  - `REMOTE_MODEL_PLANNING` - Planner JSON generation (remote)
  - `REMOTE_MODEL_FILTERING` - Schema filtering (remote)
  - `REMOTE_MODEL_ERROR_CORRECTION` - SQL error correction (remote)
  - `REMOTE_MODEL_REFINEMENT` - Query refinement (remote)
  - `LOCAL_MODEL_STRATEGY` - Pre-planner strategy generation (local)
  - `LOCAL_MODEL_PLANNING` - Planner JSON generation (local)
  - `LOCAL_MODEL_FILTERING` - Schema filtering (local)
  - `LOCAL_MODEL_ERROR_CORRECTION` - SQL error correction (local)
  - `LOCAL_MODEL_REFINEMENT` - Query refinement (local)
- Model Aliases (when `REMOTE_LLM_PROVIDER=auto`):
  - **Anthropic**: `claude-sonnet-4-5`, `claude-haiku-4-5`, `claude-opus-4-1`
  - **OpenAI**: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4o`, `gpt-4o-mini`, `o3`, `o3-mini`, `o1-mini`
  - Full model names also work (e.g., `claude-3-5-sonnet-20241022`, `gpt-4o`)
  - Auto mode automatically routes each model to the correct provider
  - Example: Mix Claude Sonnet for strategy with GPT-4o-mini for planning
- `PLANNER_COMPLEXITY` - Planner tier: `minimal` (8GB models), `standard` (13B-30B), `full` (GPT-4+/Claude)

### Database Configuration
- `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - SQL Server connection details
- `USE_TEST_DB` - Set to `true` to use SQLite test database instead of SQL Server

### Query Configuration
- `RETRY_COUNT` - Max retries for query errors (default: 3)
- `REFINE_COUNT` - Max refinement attempts for empty results (default: 3)
- `TOP_MOST_RELEVANT_TABLES` - Number of tables to retrieve via vector search (default: 8)
- `EMBEDDING_MODEL` - Embedding model for vector search (default: `text-embedding-3-small`)

### Foreign Key Inference
- `INFER_FOREIGN_KEYS` - Enable automatic FK inference for filtered tables (default: `false`)
- `FK_INFERENCE_CONFIDENCE_THRESHOLD` - Minimum confidence score for inferred FKs (default: `0.6`, range: 0.0-1.0)
- `FK_INFERENCE_TOP_K` - Number of candidate tables to consider per ID column (default: `3`)

### Chat Configuration
- `MAX_CHAT_TOOL_CALLS` - Maximum tool invocations per chat session (default: `3`)
- `REMOTE_MODEL_CHAT` / `LOCAL_MODEL_CHAT` - LLM model for chat and narrative (falls back to strategy model)

## Development Commands

### Running the Applications

**Streamlit UI:**
```bash
streamlit run streamlit_app.py
```

**FastAPI Server:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

**API Documentation:**
```
http://localhost:8000/docs
```

**Go Service (parallel implementation):**
```bash
cd go-service
go build -o sql-go-service.exe ./cmd/server
USE_TEST_DB=true PORT=8001 ./sql-go-service.exe
```

The Go service binds to port 8001 by default (Python uses 8000) so both can run side by side. The frontend's `vite.config.ts` defaults to `:8001`; override with `VITE_API_URL=http://localhost:8000 npm run dev` to hit the Python service instead.

### Testing

**Python — run all tests:**
```bash
pytest
```

**Python — run specific test file:**
```bash
pytest tests/unit/test_plan_audit.py
```

**Python — run with verbose output:**
```bash
pytest -v
```

**Go — run unit + structural tests (fast):**
```bash
cd go-service
go test -short ./...
```

**Go — include live LLM/SQLite e2e tests (needs `../.env` with API keys):**
```bash
cd go-service
go test ./...
```

**Cross-service parity check:**
```bash
# Run Python service on :8000 and Go service on :8001 in separate terminals, then:
./go-service/scripts/parity_check.sh
```
Replays prompts against both services and diffs SSE event sequence + final SQL/row counts. See `go-service/scripts/parity_prompts.txt` to add cases.

### Linting

**Check code style:**
```bash
flake8 .
```

**Lint specific files:**
```bash
flake8 agent/ database/ server.py
```

Flake8 config in `.flake8`:
- Max line length: 120 characters
- Ignores: E203 (whitespace before ':')
- Excludes: `.git`, `__pycache__`, `build`, `dist`

### Using Local LLM (Ollama)

**Setup Ollama:**
1. Install Ollama from https://ollama.com
2. Pull a model: `ollama pull qwen3:8b` (or `llama3`, `mistral`, etc.)
3. Verify Ollama is running: `curl http://localhost:11434/api/tags`

**Configure the application:**
1. Set `USE_LOCAL_LLM=true` in `.env`
2. Set `AI_MODEL=qwen3:8b` (or your preferred Ollama model)
3. Set `AI_MODEL_REFINE=qwen3:8b`
4. Set `PLANNER_COMPLEXITY=minimal` (recommended for 8GB models)
5. Optionally set `OLLAMA_BASE_URL` if using a non-default Ollama server

**Benefits:**
- No API costs (runs locally)
- No internet required
- Full data privacy
- Faster responses (no network latency)

**Switching between providers:**
- OpenAI: Set `USE_LOCAL_LLM=false`, `REMOTE_LLM_PROVIDER=openai`, and ensure `OPENAI_API_KEY` is set
- Anthropic: Set `USE_LOCAL_LLM=false`, `REMOTE_LLM_PROVIDER=anthropic`, and ensure `ANTHROPIC_API_KEY` is set
- Auto (mixed providers): Set `USE_LOCAL_LLM=false`, `REMOTE_LLM_PROVIDER=auto`, and ensure both API keys are set
  - Example configuration for mixing providers:
    ```bash
    REMOTE_LLM_PROVIDER=auto
    REMOTE_MODEL_STRATEGY=claude-sonnet-4-5        # Use Claude for complex reasoning
    REMOTE_MODEL_PLANNING=gpt-4o-mini              # Use GPT for structured output
    REMOTE_MODEL_ERROR_CORRECTION=claude-haiku-4-5 # Use Claude Haiku for quick fixes
    REMOTE_MODEL_REFINEMENT=gpt-4o-mini            # Use GPT for refinement
    ```
- Ollama: Set `USE_LOCAL_LLM=true` and ensure Ollama is running locally

### Docker

**Build:**
```bash
docker build -t sql-query-assistant .
```

**Run:**
```bash
docker run -d --env-file .env -p 8000:8000 sql-query-assistant
```

Note: When using Docker, set `DB_SERVER=host.docker.internal` to connect to local SQL Server.

## Architecture

### LangGraph Workflow

The agent uses a **LangGraph state machine workflow** (defined in `agent/create_agent.py`). The workflow adapts based on whether the query is new or a conversational follow-up.

#### New Query Workflow

1. **analyze_schema** - Retrieves full database schema with table/column metadata and foreign keys
2. **filter_schema** - Uses **vector similarity search** to find the top-k most relevant tables (default: 8)
3. **infer_foreign_keys** (optional) - Automatically infers missing FK relationships using vector similarity (only runs if `INFER_FOREIGN_KEYS=true`)
4. **format_schema_markdown** - Converts filtered schema to markdown format optimized for LLM consumption
   - Intelligent FK resolution: matches column names when PK not specified (e.g., CVEID → CVEID)
5. **pre_planner** - LLM generates text-based strategic plan:
   - High-level query strategy in natural language
   - Table selection reasoning
   - Join path explanations
   - Filter and aggregation strategy
   - Incorporates feedback from error/refinement loops
6. **planner** - LLM converts strategy to structured query plan (PlannerOutput):
   - Table selections with columns and filters
   - Join edges (foreign key relationships)
   - Aggregations (GROUP BY, HAVING)
   - ORDER BY and LIMIT specifications
   - Three operational modes: initial, update, rewrite
   - Three complexity tiers: minimal, standard, full
7. **plan_audit** - Deterministic validation and fixes (feedback loop DISABLED):
   - Validates column existence
   - Fixes orphaned filter columns
   - Completes GROUP BY clauses
   - Removes invalid joins and filters
   - Logs issues but continues execution (lets real SQL errors surface)
8. **check_clarification** - Analyzes planner decision (proceed/clarify/terminate)
9. **generate_query** - Deterministic join synthesizer using SQLGlot:
   - No LLM calls - purely algorithmic transformation
   - Builds SQL AST from PlannerOutput
   - Automatic identifier quoting for reserved keywords
   - Multi-dialect support (SQL Server, SQLite, PostgreSQL, MySQL)
10. **execute_query** - Executes the query against the database
11. **Feedback loops (strategy-first error correction):**
   - **handle_error** - Analyzes SQL errors, generates feedback, routes to **pre_planner** (max 3 iterations)
   - **refine_query** - Analyzes empty results, generates feedback, routes to **pre_planner** (max 3 iterations)
   - **generate_modification_options** - On success, generates interactive modification options
   - **cleanup** - Closes database connection and exits

#### Conversational Follow-up Workflow (Currently Disabled)

**Note**: The conversational router is currently disabled in the UI. Each query generates a new independent thread. The infrastructure remains in place for future re-enabling.

When re-enabled, the workflow would be:
1. **conversational_router** - Analyzes follow-up request in context of conversation history
   - Routes to planner with mode: "update" (minor changes) or "rewrite" (major changes)
   - Prevents SQL injection by always using planner → join synthesizer pipeline
2. **planner** (update/rewrite mode) - Generates updated plan
3. **plan_audit** → **check_clarification** → **generate_query** → **execute_query** (same as above)

### State Management

The `State` TypedDict (in `agent/state.py`) tracks:
- `messages` - LangGraph message history
- `user_questions` - List of natural language questions (conversation history)
- `queries` - List of generated SQL queries
- `planner_outputs` - List of PlannerOutput objects (plan history)
- `schema` - Database schema (full, then filtered)
- `query` - Current SQL query
- `result` - Query execution results
- `sort_order`, `result_limit`, `time_filter` - User preferences
- `router_mode` - Conversational router mode ("update" or "rewrite")
- `router_instructions` - Instructions from router to planner
- `planner_output` - Current PlannerOutput object
- `needs_clarification` - Flag for ambiguous queries
- `clarification_suggestions` - List of clarification questions
- **Feedback loop fields (strategy-first error correction):**
  - `pre_plan_strategy` - Current text-based strategy from pre-planner
  - `preplan_history` - List of previous strategies (for tracking iterations)
  - `audit_feedback` - Feedback from plan audit (currently disabled)
  - `error_feedback` - Feedback from error analysis for pre-planner
  - `refinement_feedback` - Feedback from empty results analysis for pre-planner
  - `audit_iteration` - Audit iteration counter (max: 2, currently unused)
  - `error_iteration` - Error correction iteration counter (max: 3)
  - `refinement_iteration` - Refinement iteration counter (max: 3)
  - `termination_reason` - Explanation for workflow termination
- `error_history` - List of errors encountered
- `refined_reasoning` - Explanations for refinements
- `corrected_plans` - Plans corrected during error handling
- `refined_plans` - Plans refined for empty results
- **Chat and data summary fields:**
  - `chat_session_id` - Frontend session ID (triggers narrative generation when set)
  - `data_summary` - Deterministic column-level statistics from `generate_data_summary`
  - `query_narrative` - AI-generated narrative summary of results
  - `filtered_schema` - Schema subset used for this query (also used as chat context)

### Key Components

**3-Stage Schema Filtering (`agent/filter_schema.py`):**
- **Stage 1**: Vector search creates candidate pool (top-k tables via Chroma vector store)
- **Stage 2**: LLM reasoning evaluates relevance with explanations
- **Stage 3**: FK expansion adds related tables automatically
- Uses embeddings (default: text-embedding-3-small) for vector search
- Reduces context size by 60-90%, improving accuracy and reducing costs

**Foreign Key Inference (`database/infer_foreign_keys.py`, `agent/infer_foreign_keys.py`):**
- Automatically discovers FK relationships in databases without explicit constraints
- Uses ID column naming patterns (CompanyID, TagId, Tag_ID, etc.)
- Vector similarity search to match FK columns to candidate tables
- Only runs on filtered schema (6-10 tables) for optimal performance
- Configurable confidence threshold (default: 0.6)
- Augments existing FKs without replacing them
- Each inferred FK includes confidence score and "inferred: true" flag
- **Testing**: Compare against ground truth using `python scripts/compare_fk_inference.py`

**Standalone FK Inferencing Agent (`fk_inferencing_agent/`):**
- Interactive CLI tool for discovering FKs with human-in-the-loop validation
- Built with LangGraph for stateful, interactive workflow
- Human can accept/reject/modify each proposed FK relationship
- Uses same vector similarity approach as integrated inference
- Saves validated FKs to `domain-specific-foreign-keys.json`
- Useful for one-time FK discovery or database documentation
- Run with: `python -m fk_inferencing_agent.cli`
- **See**: `fk_inferencing_agent/README.md` for detailed documentation

**FK Resolution (`agent/format_schema_markdown.py`):**
- Intelligent primary key column resolution for FK relationships
- **Resolution strategy** (applied in order):
  1. Use explicit `to_column` if specified in FK definition
  2. Look up actual primary key from referenced table's schema
  3. Try matching FK column name (e.g., CVEID → CVEID, CompanyID → CompanyID)
  4. Fall back to "ID" as last resort
- **Solves common issues**:
  - Tables without explicit PK constraints
  - Domain-specific FKs missing `to_column` specification
  - Non-standard PK column names (not "ID")
- **Example**: `CVEID → tb_CVE.CVEID` (not `tb_CVE.ID`) when tb_CVE has CVEID column
- Prevents "Invalid column name 'ID'" errors in generated SQL

**Two-Stage Planning Architecture:**

*Stage 1: Pre-Planner (`agent/pre_planner.py`):*
- Creates high-level text-based strategic plan
- Natural language description of query approach
- Table selection with reasoning
- Join path explanations
- Filter and aggregation strategy
- **Feedback Integration**: Incorporates error/refinement feedback from failed attempts
- Schema optimization: Omits schema when feedback present (already in feedback text)
- Tracks strategy history for debugging

*Stage 2: Planner (`agent/planner.py`):*
- Converts text strategy to structured JSON (PlannerOutput)
- Three complexity tiers (configured via `PLANNER_COMPLEXITY`):
  - **minimal** (8GB models): 93% token reduction, basic features
  - **standard** (13B-30B models): 61% token reduction, includes reason fields
  - **full** (GPT-4+ models): Complete feature set with window functions, CTEs, subqueries
- Three operational modes:
  - **initial**: New query, uses full filtered schema
  - **update**: Minor plan modifications, omits schema
  - **rewrite**: Major changes, uses full filtered schema
- Outputs structured PlannerOutput Pydantic model
- Auto-fix logic for common issues (unquoting SQL functions, table reference validation)

**Plan Auditing (`agent/plan_audit.py`):**
- Deterministic validation and fixes (no LLM calls)
- Validates column existence against schema
- Fixes orphaned filter columns (columns marked as "filter" but without filter predicates)
- Completes GROUP BY clauses (adds missing projection columns)
- Removes invalid joins and filters
- Filters schema to only tables in plan
- **Audit feedback loop DISABLED**: Logs issues but continues execution
  - Lets real SQL errors surface (more informative than pre-execution warnings)
  - Planner auto-fix handles most issues
  - Error feedback provides better correction guidance

**Clarification Detection (`agent/check_clarification.py`):**
- Analyzes planner decision field: "proceed", "clarify", or "terminate"
- Extracts ambiguities and clarification suggestions
- Routes to cleanup if terminated, otherwise proceeds to SQL generation

**Deterministic Join Synthesizer (`agent/generate_query.py`):**
- Uses SQLGlot AST for SQL generation (zero LLM calls)
- Builds SQL from PlannerOutput:
  1. SELECT columns (projections and aggregates)
  2. FROM clause with aliases
  3. JOIN clauses from join edges
  4. WHERE clause from filters (table-level, global, subquery, time)
  5. GROUP BY and HAVING
  6. ORDER BY (priority: plan.order_by > state.sort_order)
  7. LIMIT (priority: plan.limit > state.result_limit)
- Automatic identifier quoting: `identify=True` prevents SQL Server reserved keyword errors
- Multi-dialect support via SQLGlot

**Conversational Router (`agent/conversational_router.py`) - Currently Disabled:**
- **Status**: Code exists but is disabled in the UI workflow
- **Why**: Each query creates an independent thread for simplicity
- **Future**: May be re-enabled with improved conversation handling
- When enabled, analyzes follow-up questions using LLM
- Decides routing mode: "update" (minor changes) or "rewrite" (major changes)
- Always routes through planner → join synthesizer (prevents SQL injection)

**Error Handling (`agent/handle_tool_error.py`):**
- **Strategy-first approach**: Generates feedback for pre-planner, not JSON patches
- Analyzes SQL execution errors using LLM
- Generates `ErrorFeedback` with:
  - `error_analysis`: What went wrong (wrong column, wrong join, type mismatch, etc.)
  - `strategic_guidance`: What to change in the strategy (specific tables/columns)
- Routes back to **pre_planner** with feedback
- Iteration limit: 3 attempts (tracked via `error_iteration`)
- On exhaustion: Terminates with clear error message
- Tracks error history for debugging

**Query Refinement (`agent/refine_query.py`):**
- **Strategy-first approach**: Generates feedback for pre-planner, not JSON patches
- Triggered when query returns zero results
- Analyzes why query failed using LLM
- Generates `RefinementFeedback` with:
  - `no_results_analysis`: Why no results (too restrictive filters, wrong columns, etc.)
  - `strategic_guidance`: How to broaden the strategy to get results
- Routes back to **pre_planner** with feedback
- Iteration limit: 3 attempts (tracked via `refinement_iteration`)
- On exhaustion: Terminates with explanation
- Preserves user intent while broadening approach
- Tracks refinement history and reasoning

### Planner Complexity Tiers

The system supports three planner complexity levels (configured via `PLANNER_COMPLEXITY` environment variable):

| Tier | Models | Prompt Tokens | Features |
|------|--------|---------------|----------|
| **minimal** | qwen3:8b, llama3:8b, mistral:7b | ~265 (93% reduction) | Selections, joins, filters, GROUP BY, ORDER BY, LIMIT |
| **standard** | mixtral:8x7b, qwen2.5:14b, llama3.1:13b | ~1,500 (61% reduction) | + Reason fields for debugging |
| **full** | gpt-4o, gpt-4o-mini, claude-3.5-sonnet | ~3,832 (baseline) | + Window functions, CTEs, subqueries |

**Model Selection:**
```python
from agent.planner import get_planner_model_class

# Gets appropriate model based on PLANNER_COMPLEXITY env var
model_class = get_planner_model_class()  # PlannerOutputMinimal, PlannerOutputStandard, or PlannerOutput
```

### Database Connection

**SQL Server:**
- Uses `pyodbc` with ODBC Driver 17
- Connection managed in `database/connection.py`
- Connection is passed through workflow nodes and closed in cleanup

**Test Database:**
- SQLite database for testing (`sample-db.db`, `chinook.db`)
- Activated with `USE_TEST_DB=true`

### Domain-Specific Configuration

Domain-specific guidance helps the system understand your database schema and terminology:

**Configuration Files** (in `domain_specific_guidance/`):
- `domain-specific-guidance-instructions.json` - Maps domain terminology to database concepts
- `domain-specific-table-metadata.json` - Provides table descriptions and column metadata
- `domain-specific-foreign-keys.json` - Defines table relationships for accurate JOINs
- `domain-specific-sample-queries.json` - Sample queries for testing

See `domain_specific_guidance/README.md` for detailed configuration instructions.

### Conversational Data Assistant (Chat)

After a query completes, the system generates a narrative summary and seeds a chat conversation. Users can ask follow-up questions in the side panel. The chat agent answers from data context (summary statistics, schema, query plan) or autonomously invokes a `run_query` tool to fetch new data.

**Key Components:**
- **`agent/chat_agent.py`** — Agentic loop (`stream_chat_agentic`): binds tools → invokes LLM → detects tool calls → executes `query_database()` → yields SSE events → loops until text response
- **`agent/chat_tools.py`** — Single `@tool` definition (`run_query`) for LLM schema generation; actual execution in the agentic loop
- **`agent/generate_data_summary.py`** — Deterministic column-level statistics (no LLM): numeric (min/max/avg/median/sum), text (top values), datetime (range)
- **`server.py`** — `POST /query/chat` (SSE streaming), `POST /query/chat/reset` (clear session)

**Memory Model:**
- Backend: In-process `InMemoryChatMessageHistory` per session (ephemeral — lost on restart)
- Frontend: `localStorage` persistence via `useConversations` hook (survives browser refresh)
- Tool budget: `MAX_CHAT_TOOL_CALLS` (default: 3) per session, then tools are unbound

**Data Flow:**
1. Main query completes → `generate_data_summary` → `generate_query_narrative` (seeds chat)
2. User sends message → `POST /query/chat` → loads query state from `thread_states.json` → builds data context → agentic loop
3. If LLM calls `run_query` → full pipeline executes → status events stream to frontend → result updates main panel → LLM summarizes

**Frontend Integration:**
- `useChat` hook manages messages, streaming content, and tool status
- `useConversations` persists conversations to localStorage (messages + result IDs)
- `useResultStore` caches `QueryResult` objects for click-to-view from chat messages
- `ChatPanel` renders message types: user, assistant, tool_start, tool_result, tool_error, data_summary

See **[CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md)** for the full architecture reference.

## Code Organization

```
agent/
├── create_agent.py              # Main LangGraph workflow setup and routing logic
├── state.py                     # State TypedDict definition
├── query_database.py            # High-level query pipeline entry point
│
├── Schema Processing
├── analyze_schema.py            # Retrieve full database schema
├── filter_schema.py             # Vector search for relevant tables (top-k)
├── infer_foreign_keys.py        # Infer missing FK relationships (workflow node)
├── format_schema_markdown.py    # Convert schema to markdown for LLM
│
├── Query Planning
├── planner.py                   # LLM-based query planning (3 complexity tiers, 3 modes)
├── plan_audit.py                # Deterministic plan validation and fixes
├── check_clarification.py       # Detect ambiguities and route based on decision
│
├── Conversational Routing
├── conversational_router.py     # Route follow-up queries (update/rewrite)
│
├── Chat & Data Analysis
├── chat_agent.py                # Agentic chat loop with tool calling + narrative generation
├── chat_tools.py                # Tool definitions for chat agent (run_query)
├── generate_data_summary.py     # Deterministic column-level statistics (no LLM)
│
├── SQL Generation & Execution
├── generate_query.py            # Deterministic join synthesizer (SQLGlot)
├── execute_query.py             # Execute SQL against database
│
└── Error Handling & Refinement
    ├── handle_tool_error.py     # LLM-based SQL error correction
    └── refine_query.py          # LLM-based query improvement for empty results

models/
├── planner_output.py            # Full planner model (GPT-4+)
├── planner_output_standard.py   # Standard planner model (13B-30B)
├── planner_output_minimal.py    # Minimal planner model (8GB)
└── router_output.py             # Conversational router output

database/
├── connection.py                # Database connection management (SQL Server + SQLite)
├── introspection.py             # SQLAlchemy-based schema introspection
└── infer_foreign_keys.py        # FK inference logic (vector similarity)

utils/
├── llm_factory.py               # LLM provider abstraction (OpenAI/Anthropic/Ollama switcher)
├── logger.py                    # Structured logging configuration
├── logging_config.py            # Log formatting and handlers
├── stream_utils.py              # SSE emission utilities (emit_node_status)
└── thread_manager.py            # Thread/query state persistence (thread_states.json)

domain_specific_guidance/
├── README.md                    # Configuration guide
├── domain-specific-guidance-instructions.json
├── domain-specific-table-metadata.json
├── domain-specific-foreign-keys.json
└── domain-specific-sample-queries.json

scripts/
└── compare_fk_inference.py      # Test FK inference against ground truth

demo_frontend/src/
├── api/
│   ├── client.ts                # SSE streaming client (streamQuery, streamChat, streamPatch)
│   └── types.ts                 # TypeScript types matching FastAPI models
├── hooks/
│   ├── useQuery.ts              # Main query execution state (steps, result, status)
│   ├── useChat.ts               # Chat state management (agentic loop callbacks)
│   ├── useConversations.ts      # Multi-conversation localStorage persistence
│   └── useResultStore.ts        # QueryResult localStorage cache
├── components/
│   ├── ChatPanel.tsx            # Chat side panel UI
│   ├── WorkflowProgress.tsx     # Workflow timeline with step metadata
│   ├── QueryInput.tsx           # Natural language query input
│   ├── SqlViewer.tsx            # SQL display with syntax highlighting
│   └── ResultsTable.tsx         # Data table with sorting/pagination
└── App.tsx                      # Top-level wiring (chat ↔ query ↔ results)

tests/
└── unit/
    ├── test_combine_json_schema.py       # Schema combination tests
    ├── test_orphaned_filter_columns.py   # Orphaned filter detection tests
    ├── test_plan_audit.py                # Plan auditing tests
    ├── test_advanced_sql_generation.py   # Advanced SQL features tests
    ├── test_reserved_keywords.py         # Reserved keyword quoting tests
    ├── test_openai_schema_validation.py  # OpenAI schema compatibility tests
    ├── test_order_by_limit.py            # ORDER BY/LIMIT tests
    └── test_sqlglot_generation.py        # SQLGlot generation tests

go-service/                               # Go reimplementation — full feature parity
├── cmd/server/main.go                    # Entry point: env, logger, gin server
├── internal/
│   ├── server/                           # gin handlers + SSE
│   │   ├── server.go                     # engine, route registration, middleware
│   │   ├── middleware.go                 # request logger
│   │   ├── sse.go                        # SSE helpers (flush, Content-Type)
│   │   ├── models.go                     # QueryRequest/Response, SSE event types
│   │   ├── query_handler.go              # POST /query, /query/stream, /databases
│   │   ├── chat_handler.go               # POST /query/chat, /query/chat/reset
│   │   ├── patch_handler.go              # POST /query/patch
│   │   ├── exec_sql_handler.go           # POST /query/execute-sql
│   │   └── cancel_handler.go             # POST /cancel
│   ├── agent/
│   │   ├── graph.go                      # Hand-rolled state machine (RunQuery, RunPatch)
│   │   ├── state.go                      # Workflow State struct
│   │   └── nodes/                        # All workflow nodes
│   │       ├── prompt_context.go         # PromptContext type for LLM transparency
│   │       ├── schema.go                 # AnalyzeSchema, FormatSchemaMarkdown
│   │       ├── filter_schema.go          # 3-stage filter (vector + LLM + FK)
│   │       ├── infer_fk.go               # Optional FK inference node
│   │       ├── planning.go               # PrePlanner, Planner, PlanAudit, CheckClarification
│   │       ├── feedback.go               # HandleError, RefineQuery
│   │       ├── execution.go              # GenerateQuery, ExecuteQuery
│   │       ├── data_summary.go           # ComputeDataSummary
│   │       ├── modification_options.go   # GenerateModificationOptions
│   │       ├── narrative.go              # GenerateQueryNarrative (LLM)
│   │       └── transform_plan.go         # ApplyPatch (4 ops)
│   ├── chat/                             # Agentic chat: sessions, tools, loop
│   │   ├── session.go                    # In-memory session storage with TTL
│   │   ├── tools.go                      # run_query, respond_with_revision
│   │   └── agent.go                      # StreamChat agentic loop
│   ├── llm/                              # OpenAI + Anthropic + Ollama clients
│   │   ├── client.go                     # Client interface, ResolveModel, ModelForStage
│   │   ├── openai.go                     # OpenAI: Chat, StructuredOutput, Stream, Embed, ChatWithTools
│   │   ├── anthropic.go                  # Anthropic: same surface via tool-use
│   │   └── ollama.go                     # Ollama: chat + JSON mode (no tools)
│   ├── sql/                              # T-SQL/SQLite emitter (replaces SQLGlot)
│   │   ├── emit.go                       # Main emitter
│   │   ├── dialect.go                    # Dialect interface + TSQL/SQLite impls
│   │   └── validate.go                   # IsSelectOnly guard for /execute-sql
│   ├── schema/introspect.go              # SQLite + SQL Server pragma/INFORMATION_SCHEMA
│   ├── vector/store.go                   # Pure-Go cosine-sim vector store
│   ├── fk/                               # FK pattern detection + matcher
│   ├── cancel/registry.go                # Per-session cancel-func registry
│   ├── db/                               # Connection management + demo registry
│   ├── thread/store.go                   # thread_states.json reader/writer (compatible with Python)
│   ├── models/                           # Wire format types (PlannerOutput, DataSummary, etc.)
│   └── logger/logger.go                  # slog wrapper with ctx-scoped fields
├── scripts/
│   ├── parity_check.sh                   # Diff Python vs Go for the same prompt
│   └── parity_prompts.txt                # Prompts the parity script replays
├── README.md                             # Build, run, env vars
├── PARITY.md                             # Endpoint + node feature matrix vs Python
├── POST_MVP.md                           # Remaining deferred items
├── TEST_COVERAGE.md                      # Go test inventory mapped to Python tests
└── Dockerfile                            # Multi-stage distroless build (~30 MB)
```

## Important Patterns

### LLM Provider Factory

The `utils/llm_factory.py` module provides a `get_chat_llm()` function that abstracts LLM provider selection:
- Returns `ChatOpenAI` when `USE_LOCAL_LLM=false` and `REMOTE_LLM_PROVIDER=openai`
- Returns `ChatAnthropic` when `USE_LOCAL_LLM=false` and `REMOTE_LLM_PROVIDER=anthropic`
- Returns `ChatOllama` when `USE_LOCAL_LLM=true`
- All providers have identical LangChain APIs (`.invoke()`, `.with_structured_output()`)
- Allows seamless switching between OpenAI, Anthropic, and local Ollama LLMs

All LLM instantiation points use this factory:
```python
from utils.llm_factory import get_chat_llm

llm = get_chat_llm(model_name=os.getenv("AI_MODEL"), temperature=0.7)
structured_llm = llm.with_structured_output(PlannerOutput)
```

### Structured Outputs with Pydantic

The planner and router use Pydantic models for structured LLM outputs:
```python
from models.planner_output import PlannerOutput
from utils.llm_factory import get_structured_llm

# Get LLM with structured output support
structured_llm = get_structured_llm(PlannerOutput, model_name="gpt-4o-mini")

# Invoke returns Pydantic model instance
plan = structured_llm.invoke(messages)  # Returns PlannerOutput object
```

### Conditional Routing in LangGraph

The workflow uses multiple conditional routing functions:

**1. Initial Routing (START):**
```python
def route_from_start(state: State):
    if state.get("is_continuation"):
        return "conversational_router"
    else:
        return "analyze_schema"
```

**2. Router Routing:**
```python
def route_from_router(state: State):
    # Router always goes to planner (no inline SQL revision)
    return "planner"
```

**3. Clarification Routing:**
```python
def route_after_clarification(state: State):
    if not state.get("planner_output"):
        return "cleanup"  # Planner failed

    decision = state["planner_output"].get("decision")
    if decision == "terminate":
        return "cleanup"  # Invalid query
    else:
        return "generate_query"  # Proceed or clarify
```

**4. Execute Query Routing:**
```python
def should_continue(state: State):
    has_error = "Error" in state["messages"][-1].content
    none_result = is_none_result(state["result"])

    if has_error and state["retry_count"] < MAX_RETRY:
        return "handle_error"
    elif none_result and state["refined_count"] < MAX_REFINE:
        return "refine_query"
    else:
        return "cleanup"
```

### Deterministic Plan Auditing

The `plan_audit` node fixes common planner mistakes without LLM calls:
- Validates all columns exist in schema
- Removes orphaned filter columns (marked as "filter" but no FilterPredicate)
- Completes GROUP BY clauses (adds missing projection columns)
- Removes invalid joins (columns don't exist)
- Filters schema to only tables in plan

This catches 80-90% of errors before SQL generation, reducing retry cycles.

### Reserved Keyword Handling

SQL Server reserved keywords (like "Index", "Order", "Key", "Table") are automatically quoted:
```python
# In generate_query.py
sql_str = query.sql(dialect="tsql", pretty=True, identify=True)
# identify=True quotes all identifiers: Index → [Index]
```

### ORDER BY and LIMIT Support

The planner can now generate ORDER BY and LIMIT directly from natural language:
```python
# User query: "Last 10 logins"
planner_output = {
    "order_by": [{"table": "tb_Logins", "column": "LoginDate", "direction": "DESC"}],
    "limit": 10
}

# Join synthesizer uses priority:
# 1. plan.order_by > state.sort_order
# 2. plan.limit > state.result_limit
```

## Testing Notes

- `conftest.py` adds project root to Python path for imports
- Unit tests use pytest fixtures
- Test database queries available in `test-db-queries.json`
- All 87 tests must pass before merging PRs

### Running Specific Test Suites

```bash
# Plan auditing
pytest tests/unit/test_plan_audit.py -v

# Reserved keywords
pytest tests/unit/test_reserved_keywords.py -v

# ORDER BY/LIMIT
pytest tests/unit/test_order_by_limit.py -v

# OpenAI schema validation
pytest tests/unit/test_openai_schema_validation.py -v
```

## Additional Documentation

### Core Documentation
- **[README.md](README.md)**: Comprehensive project overview, installation, and usage guide
- **[WORKFLOW_DIAGRAM.md](WORKFLOW_DIAGRAM.md)**: Visual workflow diagrams and architecture explanation
- **[JOIN_SYNTHESIZER.md](JOIN_SYNTHESIZER.md)**: Detailed SQL generation architecture and join synthesis
- **[CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md)**: Conversational data assistant — agentic loop, tool calling, session management, frontend integration

### Go Service Documentation
- **[go-service/README.md](go-service/README.md)**: Go service overview, build & run instructions, env vars
- **[go-service/PARITY.md](go-service/PARITY.md)**: Endpoint + node feature matrix vs Python
- **[go-service/POST_MVP.md](go-service/POST_MVP.md)**: Remaining deferred items (CTEs, planner tiers, optional Eino migration)
- **[go-service/TEST_COVERAGE.md](go-service/TEST_COVERAGE.md)**: Go test inventory mapped to Python tests

### Specialized Topics
- **[domain_specific_guidance/README.md](domain_specific_guidance/README.md)**: Configuration guide for domain-specific customization

### Key Architectural Concepts

🔹 **Deterministic Join Synthesizer**: SQLGlot-based SQL generation (no LLM, instant, zero cost)
🔹 **Schema Filtering**: Vector search reduces context from full schema to top-k relevant tables
🔹 **Planner Complexity Tiers**: Three levels optimized for different model sizes (93% token reduction for minimal)
🔹 **Plan Auditing**: Automatic validation and fixing of common planner mistakes (catches 80-90% of errors)
🔹 **Conversational Data Assistant**: Agentic chat loop with `run_query` tool calling, data context injection, and narrative generation
🔹 **SQL Server Safety**: Automatic identifier quoting prevents reserved keyword errors
🔹 **LLM Provider Abstraction**: Seamless switching between OpenAI, Anthropic, and Ollama

## Common Development Tasks

> **Reminder:** All "major" tasks below MUST land in both Python and Go. See [Dual Implementation](#-dual-implementation-project--read-this-first) at the top for the full parity rule.

### Adding a New Planner Feature

**Python:**
1. Update Pydantic model in `models/planner_output.py` (and minimal/standard variants)
2. Update planner prompt in `agent/planner.py`
3. Update join synthesizer in `agent/generate_query.py` to handle new feature
4. Add unit tests in `tests/unit/`
5. Update documentation in `WORKFLOW_DIAGRAM.md` and `JOIN_SYNTHESIZER.md`

**Go (mirror the change):**
1. Update the `PlannerOutput` struct in `go-service/internal/models/planner_output.go`
2. Regenerate the JSON schema by re-running tests — `invopop/jsonschema` reflects from the struct automatically
3. Update planner prompt in `go-service/internal/agent/nodes/planning.go` to match Python's prompt changes
4. Update T-SQL emitter in `go-service/internal/sql/emit.go`
5. Add unit tests in `go-service/internal/sql/emit_*_test.go`
6. Update `go-service/PARITY.md` matrix entry

### Adding a New Workflow Node

**Python:**
1. Create node function in `agent/your_node.py`
2. Add node to workflow in `agent/create_agent.py`:
   ```python
   workflow.add_node("your_node", your_node_function)
   workflow.add_edge("previous_node", "your_node")
   ```
3. Update `State` TypedDict in `agent/state.py` if needed
4. If the node calls an LLM, emit `prompt_context` via `emit_node_status(metadata={"prompt_context": {...}})` so the frontend's `PromptViewer` can render it
5. Add tests and update `WORKFLOW_DIAGRAM.md`

**Go (mirror the change):**
1. Create node function in `go-service/internal/agent/nodes/your_node.go`. If it uses an LLM, return `(*PromptContext, error)` alongside the result — see `nodes/planning.go:PrePlanner` for the pattern.
2. Add node to the orchestrator in `go-service/internal/agent/graph.go:RunQuery`
3. Update `State` struct in `go-service/internal/agent/state.go` if needed
4. Pipe `prompt_context` through the `emit(...)` metadata using the `withPrompt(...)` helper in `graph.go`
5. If the node has wire-format output, add a struct in `go-service/internal/models/` and an `omitempty` field on `QueryResponse` in `go-service/internal/server/models.go`
6. Add unit tests in `go-service/internal/agent/nodes/`

### Adding a New Endpoint

**Python:**
1. Add request/response Pydantic models in `server.py`
2. Add route handler in `server.py`
3. Add tests under `tests/`

**Go (mirror the change):**
1. Add a new `*_handler.go` file in `go-service/internal/server/` (one file per logical endpoint group)
2. Register the route in `go-service/internal/server/server.go:registerRoutes`
3. Add request/response structs to `go-service/internal/server/models.go` — match the Python JSON shape exactly (including `json:"omitempty"` patterns)
4. If the endpoint streams SSE, follow the pattern in `query_handler.go:queryStreamHandler` (channel + goroutine + per-event `sendSSE`)
5. Add a live e2e test under `go-service/internal/server/*_e2e_test.go`
6. Update `go-service/PARITY.md` with the new endpoint row

### Debugging Workflow Issues

1. Check debug files in `debug/`:
   - `debug_generated_planner_output.json` - Raw planner output
   - `debug_generated_sql.txt` - Generated SQL
   - `debug_schema_markdown.md` - Filtered schema sent to planner

2. Enable verbose logging:
   ```python
   logger.setLevel(logging.DEBUG)
   ```

3. Use LangGraph visualization:
   ```python
   from agent.create_agent import create_sql_agent
   agent = create_sql_agent()
   # Visualize workflow graph
   agent.get_graph().print_ascii()
   ```

## Performance Considerations

- Schema filtering reduces planner token usage by 60-90%
- Deterministic join synthesizer has zero LLM cost and <10ms latency
- Plan auditing prevents 80-90% of errors, reducing retry cycles
- Planner complexity tiers reduce token usage by up to 93% for small models

## Security Considerations

- SQL injection prevented by:
  1. No inline SQL revision (all queries go through planner → join synthesizer)
  2. SQLGlot AST-based SQL generation (no string concatenation)
  3. Automatic identifier quoting
- Database credentials stored in `.env` (not committed to git)
- API keys (OpenAI, Anthropic) stored in `.env` (not committed to git)
