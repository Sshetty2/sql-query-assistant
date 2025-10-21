# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **SQL Query Assistant** that converts natural language queries into SQL and executes them against a SQL Server database. It uses **LangGraph** for workflow orchestration, **LangChain** with **OpenAI** for query generation, and provides both a **Streamlit UI** and **FastAPI** backend.

## Environment Setup

Required environment variables (see `.env` file):

### LLM Provider Configuration
- `USE_LOCAL_LLM` - Set to `true` to use local Ollama, `false` for OpenAI (default: `false`)
- `OPENAI_API_KEY` - OpenAI API key (required when `USE_LOCAL_LLM=false`)
- `OLLAMA_BASE_URL` - Ollama server URL (default: `http://localhost:11434`, only used when `USE_LOCAL_LLM=true`)

### Model Selection
- `AI_MODEL` - Primary model for query generation
  - When using OpenAI: `gpt-4o-mini`, `gpt-4o`, etc.
  - When using Ollama: `qwen3:8b`, `llama3`, `mistral`, etc.
- `AI_MODEL_REFINE` - Model for query refinement (same format as AI_MODEL)
- `EMBEDDING_MODEL` - Model for vector search (deprecated - not currently used)

### Database Configuration
- `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - SQL Server connection details
- `USE_TEST_DB` - Set to `true` to use SQLite test database instead of SQL Server

### Query Configuration
- `RETRY_COUNT` - Max retries for query errors (default: 3)
- `REFINE_COUNT` - Max refinement attempts for empty results (default: 3)
- `TOP_MOST_RELEVANT_TABLES` - Number of tables to retrieve via vector search (default: 3)

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
pytest tests/unit/test_combine_json_schema.py
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
4. Optionally set `OLLAMA_BASE_URL` if using a non-default Ollama server

**Benefits:**
- No API costs (runs locally)
- No internet required
- Full data privacy
- Faster responses (no network latency)

**Switching between providers:**
- OpenAI: Set `USE_LOCAL_LLM=false` and ensure `OPENAI_API_KEY` is set
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

The agent uses a **state machine workflow** (defined in `agent/create_agent.py`) with the following nodes:

1. **analyze_schema** - Retrieves full database schema with table/column metadata
2. **filter_schema** - Uses **vector similarity search** to find the most relevant tables for the user's query
3. **generate_query** - Generates SQL query using LLM with filtered schema context
4. **execute_query** - Executes the query against the database
5. **Conditional routing:**
   - **handle_error** - Corrects SQL syntax/execution errors (loops back to execute)
   - **refine_query** - Refines query if results are empty/None (loops back to execute)
   - **cleanup** - Closes database connection and exits

### State Management

The `State` TypedDict (in `agent/state.py`) tracks:
- `messages` - Conversation history for the agent
- `user_question` - Original natural language query
- `schema` - Database schema (full, then filtered)
- `query` - Current SQL query
- `result` - Query execution results
- `sort_order`, `result_limit`, `time_filter` - User preferences
- `corrected_queries` - History of error corrections
- `refined_queries` - History of query refinements
- `retry_count`, `refined_count` - Iteration counters
- `error_history` - List of errors encountered
- `refined_reasoning` - Explanations for refinements

### Key Components

**Schema Filtering (`agent/filter_schema.py`):**
- Creates in-memory vector store from table schemas
- Uses embeddings to find top-k most relevant tables
- Reduces context size for LLM, improving accuracy and cost

**Query Generation (`agent/generate_query.py`):**
- Takes filtered schema + user question + preferences
- Generates SQL with proper sorting, limits, time filtering

**Error Handling (`agent/handle_tool_error.py`):**
- Analyzes SQL execution errors
- Uses LLM to correct syntax/semantic issues
- Tracks correction history

**Query Refinement (`agent/refine_query.py`):**
- Triggered when query returns no results
- Analyzes why query failed (e.g., wrong filters, missing joins)
- Generates improved query

### Database Connection

**SQL Server:**
- Uses `pyodbc` with ODBC Driver 17
- Connection managed in `database/connection.py`
- Connection is passed through workflow nodes and closed in cleanup

**Test Database:**
- SQLite database for testing (`sample-db.db`, `chinook.db`)
- Activated with `USE_TEST_DB=true`

### Metadata Files

- `cwp_table_metadata.json` - Table descriptions and column metadata for schema enrichment
- `cwp_foreign_keys.json` - Foreign key relationships between tables
- `test-db-queries.json`, `cwp_sample_queries.json` - Sample queries for testing

## Code Organization

```
agent/
├── create_agent.py         # Main LangGraph workflow setup
├── state.py                # State TypedDict definition
├── analyze_schema.py       # Retrieve database schema
├── filter_schema.py        # Vector search for relevant tables
├── generate_query.py       # LLM-based SQL generation
├── execute_query.py        # Execute SQL against database
├── handle_tool_error.py    # Error correction logic
├── refine_query.py         # Query refinement for empty results
├── query_database.py       # High-level query pipeline entry point
└── combine_json_schema.py  # Utility to merge schema + metadata

database/
└── connection.py           # Database connection management

utils/
└── llm_factory.py          # LLM provider factory (OpenAI/Ollama switcher)

tests/
└── unit/
    └── test_combine_json_schema.py  # Unit tests for schema utilities

server.py                   # FastAPI REST API
streamlit_app.py            # Streamlit web UI
```

## Important Patterns

**LLM Provider Factory:**
The `utils/llm_factory.py` module provides a `get_chat_llm()` function that abstracts LLM provider selection:
- Returns `ChatOpenAI` when `USE_LOCAL_LLM=false`
- Returns `ChatOllama` when `USE_LOCAL_LLM=true`
- Both providers have identical LangChain APIs (`.invoke()`, `.with_structured_output()`)
- Allows seamless switching between cloud and local LLMs

All LLM instantiation points use this factory:
```python
from utils.llm_factory import get_chat_llm

llm = get_chat_llm(model_name=os.getenv("AI_MODEL"), temperature=0.7)
structured_llm = llm.with_structured_output(PlannerOutput)
```

**Conditional Routing:**
The workflow uses `should_continue()` in `agent/create_agent.py` to decide next steps:
- Checks if error occurred AND retry count < max → go to `handle_error`
- Checks if result is None AND refined count < max → go to `refine_query`
- Otherwise → go to `cleanup`

**None Result Detection:**
The `is_none_result()` function handles different database formats:
- SQL Server: checks if `result[0][0] is None`
- SQLite: checks if `result[0][0] == "[]"` (JSON array string)

**Vector Search for Schema:**
Instead of passing entire schema to LLM, the system:
1. Embeds all table descriptions
2. Embeds user query
3. Retrieves top-k similar tables
4. Only passes relevant tables to LLM

This significantly reduces token usage and improves query accuracy.

## Testing Notes

- `conftest.py` adds project root to Python path for imports
- Unit tests use pytest fixtures
- Test database queries available in `test-db-queries.json`

## Additional Documentation

### JOIN Synthesizer
For detailed information about the SQL generation component (the "join synthesizer"), see **[JOIN_SYNTHESIZER.md](JOIN_SYNTHESIZER.md)**. This document covers:
- How the planner output is transformed into SQL deterministically
- Multi-dialect support (SQL Server, SQLite, PostgreSQL, MySQL)
- Advanced SQL features (aggregations, window functions, subqueries, CTEs)
- Performance characteristics and cost savings
- SQL injection prevention and security

### Dialect Compatibility
See **[DIALECT_FIXES_SUMMARY.md](DIALECT_FIXES_SUMMARY.md)** for:
- Recent fixes for SQL Server compatibility
- ILIKE → LIKE conversion
- DATEADD syntax corrections
- SQL injection prevention measures
- Dialect-specific handling strategies
