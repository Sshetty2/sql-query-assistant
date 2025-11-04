# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **SQL Query Assistant** that converts natural language queries into SQL and executes them against a SQL Server database. It uses **LangGraph** for workflow orchestration, **LangChain** with **OpenAI/Anthropic/Ollama** for query planning, **SQLGlot** for deterministic SQL generation, and provides both a **Streamlit UI** and **FastAPI** backend.

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

### Testing

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest tests/unit/test_plan_audit.py
```

**Run with verbose output:**
```bash
pytest -v
```

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
  - `needs_termination` - Flag for iteration exhaustion
  - `termination_reason` - Explanation for workflow termination
- `error_history` - List of errors encountered
- `refined_reasoning` - Explanations for refinements
- `corrected_plans` - Plans corrected during error handling
- `refined_plans` - Plans refined for empty results

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
└── logging_config.py            # Log formatting and handlers

domain_specific_guidance/
├── README.md                    # Configuration guide
├── domain-specific-guidance-instructions.json
├── domain-specific-table-metadata.json
├── domain-specific-foreign-keys.json
└── domain-specific-sample-queries.json

scripts/
└── compare_fk_inference.py      # Test FK inference against ground truth

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

### Specialized Topics
- **[domain_specific_guidance/README.md](domain_specific_guidance/README.md)**: Configuration guide for domain-specific customization

### Key Architectural Concepts

🔹 **Deterministic Join Synthesizer**: SQLGlot-based SQL generation (no LLM, instant, zero cost)
🔹 **Schema Filtering**: Vector search reduces context from full schema to top-k relevant tables
🔹 **Planner Complexity Tiers**: Three levels optimized for different model sizes (93% token reduction for minimal)
🔹 **Plan Auditing**: Automatic validation and fixing of common planner mistakes (catches 80-90% of errors)
🔹 **Conversational Flow**: Stateful query refinement through follow-up questions
🔹 **SQL Server Safety**: Automatic identifier quoting prevents reserved keyword errors
🔹 **LLM Provider Abstraction**: Seamless switching between OpenAI, Anthropic, and Ollama

## Common Development Tasks

### Adding a New Planner Feature

1. Update Pydantic model in `models/planner_output.py` (and minimal/standard variants)
2. Update planner prompt in `agent/planner.py`
3. Update join synthesizer in `agent/generate_query.py` to handle new feature
4. Add unit tests in `tests/unit/`
5. Update documentation in `WORKFLOW_DIAGRAM.md` and `JOIN_SYNTHESIZER.md`

### Adding a New Workflow Node

1. Create node function in `agent/your_node.py`
2. Add node to workflow in `agent/create_agent.py`:
   ```python
   workflow.add_node("your_node", your_node_function)
   workflow.add_edge("previous_node", "your_node")
   ```
3. Update `State` TypedDict in `agent/state.py` if needed
4. Add tests and update `WORKFLOW_DIAGRAM.md`

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
