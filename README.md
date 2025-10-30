# SQL Query Assistant

A sophisticated natural language to SQL query system powered by **LangGraph**, **LangChain**, and **OpenAI/Ollama**, featuring deterministic SQL generation, automatic foreign key inference, and intelligent 3-stage schema filtering.

---

## Overview

The SQL Query Assistant converts natural language questions into executable SQL queries using a multi-stage workflow:

1. **3-Stage Schema Filtering**: Vector search + LLM reasoning + FK expansion identifies the most relevant tables
2. **Foreign Key Inference** (optional): Automatically discovers missing FK relationships for better JOINs
3. **Query Planning**: LLM generates a structured query plan with tables, joins, filters, and aggregations
4. **Plan Validation**: Deterministic auditing catches and fixes common planning mistakes
5. **SQL Generation**: Deterministic join synthesizer uses SQLGlot to generate safe, valid SQL
6. **Execution & Refinement**: Executes queries with automatic error correction and result refinement

Each query is independent with a persisted history sidebar for viewing past results.

---

## Key Features

### Core Capabilities
- **Natural Language Querying**: Convert plain English into SQL queries
- **Query History**: Persisted sidebar showing recent queries with clickable results
- **Deterministic SQL Generation**: Uses SQLGlot AST for guaranteed valid SQL (no LLM for SQL generation)
- **3-Stage Schema Filtering**: Vector search + LLM reasoning + FK expansion reduces context to only relevant tables
- **Foreign Key Inference**: Automatically discovers missing FK relationships for databases without explicit constraints
  - **Integrated mode**: Optional automatic inference during queries (`INFER_FOREIGN_KEYS=true`)
  - **Standalone tool**: Interactive CLI for human-validated FK discovery ([see docs](fk_inferencing_agent/README.md))
- **Smart Error Handling**: Automatic SQL error detection and correction
- **Query Refinement**: Improves queries that return empty results
- **Clarification Detection**: Identifies ambiguous requests before execution

### Query Features
- **Plan Patching**: Instant query modifications without re-planning
  - **Add/Remove Columns**: Toggle columns on/off with checkboxes
  - **Modify ORDER BY**: Change sorting with dropdown controls
  - **Adjust LIMIT**: Fine-tune row limits with slider
  - **Instant Updates**: <2 second re-execution (vs 30+ seconds for full re-planning)
  - **Zero Cost**: Deterministic transformations without LLM calls
- **Complex Joins**: Automatic JOIN synthesis from foreign key relationships
- **Aggregations**: GROUP BY, HAVING, and aggregate functions (COUNT, SUM, AVG, MIN, MAX)
- **Ordering & Limiting**: Planner generates ORDER BY and LIMIT from requests like "last 10 logins"
- **Time Filtering**: Built-in support for time-based queries
- **Window Functions**: ROW_NUMBER, RANK, DENSE_RANK with PARTITION BY (full complexity mode)
- **Subqueries & CTEs**: Complex nested queries (full complexity mode)

### User Interfaces
- **Streamlit UI**: Interactive web interface with query history sidebar
- **FastAPI Server**: REST API for programmatic access
- **FK Inferencing Agent CLI**: Interactive tool for discovering and validating foreign keys
- **CSV Export**: Download query results for offline analysis

### LLM Support
- **OpenAI Models**: GPT-4o, GPT-4o-mini, GPT-4-turbo
- **Local Models (Ollama)**: qwen3:8b, llama3, mixtral, mistral (privacy-first, no API costs)
- **Planner Complexity Tiers**: Three levels optimized for different model sizes
  - **Minimal** (8GB models): 93% token reduction
  - **Standard** (13B-30B models): 61% token reduction
  - **Full** (GPT-4+ models): Complete feature set

---

## Prerequisites

- **Python 3.10+**
- **SQL Server** with ODBC Driver 17 (or SQLite for testing)
- **OpenAI API key** (if using OpenAI models)
- **Ollama** (if using local models) - [Installation Guide](https://ollama.com)

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/sql-query-assistant.git
cd sql-query-assistant
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# LLM Provider Configuration
USE_LOCAL_LLM=false                    # Set to "true" for Ollama, "false" for OpenAI
OPENAI_API_KEY=your_api_key_here       # Required if USE_LOCAL_LLM=false
OLLAMA_BASE_URL=http://localhost:11434 # Only used if USE_LOCAL_LLM=true

# Model Selection
AI_MODEL=gpt-4o-mini                   # OpenAI: gpt-4o-mini, gpt-4o | Ollama: qwen3:8b, llama3
AI_MODEL_REFINE=gpt-4o-mini           # Model for query refinement

# Planner Complexity Level
# Options: minimal (8GB models), standard (13B-30B), full (GPT-4+)
PLANNER_COMPLEXITY=full

# Database Configuration
DB_SERVER=localhost
DB_NAME=your_database_name
DB_USER=sa
DB_PASSWORD=your_password
USE_TEST_DB=false                      # Set to "true" to use SQLite test database

# Query Configuration
RETRY_COUNT=3                          # Max error correction attempts
REFINE_COUNT=3                         # Max refinement attempts for empty results
TOP_MOST_RELEVANT_TABLES=8             # Number of tables to retrieve via vector search

# Embedding Model
EMBEDDING_MODEL=text-embedding-3-small
```

### 4. Configure Domain-Specific Guidance (Recommended)

Domain-specific guidance helps the system understand your database schema and terminology:

```bash
cd domain_specific_guidance

# Copy example files
cp domain-specific-guidance-instructions.example.json domain-specific-guidance-instructions.json
cp domain-specific-table-metadata.example.json domain-specific-table-metadata.json
cp domain-specific-foreign-keys.example.json domain-specific-foreign-keys.json

# Edit these files to match your database
# See domain_specific_guidance/README.md for detailed instructions
```

**What these files do:**
- **domain-specific-guidance-instructions.json**: Maps domain terminology to database concepts
- **domain-specific-table-metadata.json**: Provides table descriptions and column metadata
- **domain-specific-foreign-keys.json**: Defines table relationships for accurate JOINs

📖 **For detailed configuration, see [domain_specific_guidance/README.md](domain_specific_guidance/README.md)**

---

## Usage

### Streamlit Web Interface

Start the interactive web UI:

```bash
streamlit run streamlit_app.py
```

Navigate to `http://localhost:8501` and:
1. Enter a natural language question or select from sample queries
2. Customize query parameters (sort order, result limit, time filter)
3. Click "Ask Question" to generate and execute the query
4. View results in an interactive table
5. Use the **"🔧 Modify Query"** expander to:
   - Add/remove columns with checkboxes
   - Change sorting with dropdown
   - Adjust row limits with slider
   - See instant updates (<2 seconds)
6. Export results to CSV
7. View query history in the sidebar to revisit past queries

**Plan Patching Usage Example:**
```
1. Ask: "Show me all tracks with their genre"
   [Results displayed with Name, Genre columns]

2. Click "🔧 Modify Query" → "📊 Columns" tab
   → Check "Composer" and "Milliseconds"
   [Results instantly updated with new columns]

3. Switch to "🔀 Sort & Limit" tab
   → Select "Milliseconds" and "DESC"
   → Click "Apply Sorting"
   [Results sorted by duration, longest first]

4. Adjust slider to 50 rows → Click "Apply Limit"
   [Results limited to top 50 longest tracks]
```

**Note:** Each query creates an independent thread. Conversational routing is currently disabled.

### FastAPI REST API

Start the API server:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

#### API Endpoints

**Interactive Documentation:**
```
http://localhost:8000/docs
```

**Query Endpoint:**
```bash
POST /query
Content-Type: application/json

{
  "question": "Show me all active users",
  "sort_order": "Ascending",
  "result_limit": 100,
  "time_filter": "Last 30 Days"
}
```

**Conversational Query Endpoint:**
```bash
POST /query
Content-Type: application/json

{
  "question": "Add email column",
  "previous_state": { ... }  // State from previous query
}
```

---

## Docker Deployment

### 1. Configure Environment

Set up `.env` file with Docker-specific settings:

```bash
OPENAI_API_KEY=your_api_key_here
DB_SERVER=host.docker.internal  # Special hostname for Docker
DB_NAME=your_database_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

### 2. Build and Run

```bash
# Build the Docker image
docker build -t sql-query-assistant .

# Run the container
docker run -d --env-file .env -p 8000:8000 sql-query-assistant
```

Access the API at `http://localhost:8000/docs`

---

## Project Structure

```
sql-query-assistant/
├── streamlit_app.py              # Streamlit web interface
├── server.py                     # FastAPI REST API server
├── .env                          # Environment configuration
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker container configuration
│
├── agent/                        # Core query processing workflow
│   ├── create_agent.py           # LangGraph workflow orchestration
│   ├── state.py                  # State management and TypedDict definitions
│   ├── query_database.py         # Main entry point for query pipeline
│   │
│   │── Schema Processing
│   ├── analyze_schema.py         # Retrieve full database schema
│   ├── filter_schema.py          # Vector search for relevant tables
│   ├── format_schema_markdown.py # Convert schema to LLM-friendly format
│   │
│   │── Query Planning
│   ├── planner.py                # LLM-based query planning (3 complexity tiers)
│   ├── plan_audit.py             # Deterministic plan validation and fixes
│   ├── check_clarification.py    # Detect ambiguities before execution
│   │
│   │── Conversational Routing
│   ├── conversational_router.py  # Route follow-up queries (update/rewrite)
│   │
│   │── SQL Generation & Execution
│   ├── generate_query.py         # Deterministic join synthesizer (SQLGlot)
│   ├── execute_query.py          # Execute SQL and return results
│   │
│   │── Error Handling & Refinement
│   ├── handle_tool_error.py      # LLM-based SQL error correction
│   ├── refine_query.py           # Improve queries with empty results
│
├── models/                       # Pydantic models for structured outputs
│   ├── planner_output.py         # Full planner model (GPT-4+)
│   ├── planner_output_standard.py# Standard planner model (13B-30B)
│   ├── planner_output_minimal.py # Minimal planner model (8GB)
│   ├── router_output.py          # Conversational router output
│
├── database/                     # Database connection management
│   ├── connection.py             # SQL Server and SQLite connections
│
├── utils/                        # Utility modules
│   ├── llm_factory.py            # LLM provider abstraction (OpenAI/Ollama)
│   ├── logger.py                 # Structured logging configuration
│   ├── logging_config.py         # Log formatting and handlers
│
├── domain_specific_guidance/     # Domain configuration
│   ├── README.md                 # Configuration guide
│   ├── domain-specific-guidance-instructions.json
│   ├── domain-specific-table-metadata.json
│   ├── domain-specific-foreign-keys.json
│
├── tests/                        # Unit tests
│   └── unit/
│       ├── test_combine_json_schema.py
│       ├── test_orphaned_filter_columns.py
│       ├── test_plan_audit.py
│       ├── test_advanced_sql_generation.py
│       ├── test_reserved_keywords.py
│       ├── test_openai_schema_validation.py
│       ├── test_order_by_limit.py
│       └── test_sqlglot_generation.py
│
└── docs/                         # Documentation
    ├── WORKFLOW_DIAGRAM.md       # Visual workflow diagrams
    ├── JOIN_SYNTHESIZER.md       # SQL generation architecture
    ├── CLAUDE.md                 # Developer guide
    └── domain_specific_guidance/ # Domain configuration guide
```

---

## Architecture

The SQL Query Assistant uses a **LangGraph state machine** to orchestrate a multi-stage query processing pipeline. The workflow adapts based on whether the query is new or a conversational follow-up.

### High-Level Architecture

```
User Question → Schema Filtering → Query Planning → Plan Validation →
SQL Generation → Execution → Error Handling/Refinement → Results
```

### Core Components

#### 1. Schema Processing Pipeline

**analyze_schema** → **filter_schema** → **format_schema_markdown**

- Retrieves full database schema (tables, columns, foreign keys)
- Uses vector search to filter to top-k most relevant tables
- Converts schema to markdown format optimized for LLM consumption

#### 2. Query Planning

**planner** → **plan_audit** → **check_clarification**

- **planner**: LLM generates structured query plan (PlannerOutput)
  - Supports 3 complexity tiers (minimal/standard/full)
  - Three operational modes: initial, update, rewrite
  - Outputs: table selections, join edges, filters, GROUP BY, ORDER BY, LIMIT

- **plan_audit**: Deterministic validation and fixes
  - Validates column existence
  - Fixes orphaned filter columns
  - Completes GROUP BY clauses
  - Removes invalid joins and filters

- **check_clarification**: Analyzes ambiguities
  - Checks decision field (proceed/clarify/terminate)
  - Routes to SQL generation or cleanup

#### 3. SQL Generation (Join Synthesizer)

**generate_query**

- Deterministic transformation using SQLGlot AST
- No LLM calls - purely algorithmic
- Builds SQL from PlannerOutput:
  - SELECT columns (projections and aggregates)
  - FROM clause with aliases
  - JOIN clauses from join edges
  - WHERE clause from filters
  - GROUP BY and HAVING
  - ORDER BY and LIMIT
- Automatic identifier quoting for SQL Server reserved keywords
- Multi-dialect support (SQL Server, SQLite, PostgreSQL, MySQL)

#### 4. Execution & Error Handling

**execute_query** → **handle_error** / **refine_query**

- Executes SQL against database
- Stores query in history
- Routes based on result:
  - **Error**: handle_error (LLM-based SQL correction)
  - **Empty Result**: refine_query (LLM-based query improvement)
  - **Success**: cleanup (close connection, return results)

#### 5. Conversational Routing

**conversational_router**

- Analyzes follow-up questions in context of conversation history
- Routes to planner with appropriate mode:
  - **update**: Minor changes (add/remove columns, filters)
  - **rewrite**: Major changes (different tables, new domain)
- Prevents SQL injection by always using planner → join synthesizer pipeline

### Planner Complexity Tiers

The system supports three planner complexity levels for different model sizes:

| Tier | Models | Prompt Tokens | Features |
|------|--------|---------------|----------|
| **minimal** | qwen3:8b, llama3:8b, mistral:7b | ~265 (93% reduction) | Basic queries, GROUP BY, ORDER BY, LIMIT |
| **standard** | mixtral:8x7b, qwen2.5:14b | ~1,500 (61% reduction) | + Reason fields for debugging |
| **full** | gpt-4o, gpt-4o-mini, claude | ~3,832 (baseline) | + Window functions, CTEs, subqueries |

Configure via `PLANNER_COMPLEXITY` environment variable.

---

## Workflow

The complete workflow varies based on whether the query is new or a conversational follow-up:

### New Query Flow

```
START
  ↓
analyze_schema (get full schema)
  ↓
filter_schema (vector search for relevant tables)
  ↓
format_schema_markdown (convert to markdown)
  ↓
planner (generate query plan)
  ↓
plan_audit (validate and fix)
  ↓
check_clarification (analyze ambiguities)
  ↓
generate_query (deterministic SQL generation)
  ↓
execute_query
  ↓
[Success] → cleanup → END
[Error] → handle_error → generate_query (retry)
[Empty] → refine_query → generate_query (improve)
```

### Conversational Follow-up Flow

```
START
  ↓
conversational_router (analyze follow-up)
  ↓
[update/rewrite] → planner (with router mode)
  ↓
plan_audit → check_clarification → generate_query → execute_query
  ↓
[Success/Error/Empty] → (same as above)
```

📊 **For detailed workflow diagrams, see [WORKFLOW_DIAGRAM.md](WORKFLOW_DIAGRAM.md)**

---

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Suite

```bash
pytest tests/unit/test_plan_audit.py -v
```

### Test Coverage Areas

- **Schema Processing**: Schema combination and filtering
- **Plan Auditing**: Column validation, orphaned filter detection
- **SQL Generation**: Join synthesis, aggregations, window functions
- **Reserved Keywords**: SQL Server identifier quoting
- **OpenAI Schema Validation**: Pydantic model compatibility
- **ORDER BY/LIMIT**: Query ordering and limiting

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `USE_LOCAL_LLM` | Use Ollama instead of OpenAI | `false` | `true` |
| `OPENAI_API_KEY` | OpenAI API key | - | `sk-proj-...` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` | - |
| `AI_MODEL` | Primary LLM model | - | `gpt-4o-mini` or `qwen3:8b` |
| `AI_MODEL_REFINE` | Refinement LLM model | - | `gpt-4o-mini` |
| `PLANNER_COMPLEXITY` | Planner tier | `full` | `minimal`, `standard`, `full` |
| `DB_SERVER` | Database server | `localhost` | `my-server.com` |
| `DB_NAME` | Database name | - | `saasdb` |
| `DB_USER` | Database user | `sa` | - |
| `DB_PASSWORD` | Database password | - | - |
| `USE_TEST_DB` | Use SQLite test DB | `false` | `true` |
| `RETRY_COUNT` | Max error retries | `3` | - |
| `REFINE_COUNT` | Max refinement attempts | `3` | - |
| `TOP_MOST_RELEVANT_TABLES` | Vector search top-k | `8` | - |
| `EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` | - |

### Using Local Models (Ollama)

1. Install Ollama: https://ollama.com
2. Pull a model: `ollama pull qwen3:8b`
3. Verify: `curl http://localhost:11434/api/tags`
4. Configure `.env`:
   ```bash
   USE_LOCAL_LLM=true
   AI_MODEL=qwen3:8b
   AI_MODEL_REFINE=qwen3:8b
   PLANNER_COMPLEXITY=minimal  # Recommended for 8GB models
   ```

---

## Documentation

### Primary Documentation

- **[WORKFLOW_DIAGRAM.md](WORKFLOW_DIAGRAM.md)**: Comprehensive workflow diagrams and architecture explanation
- **[JOIN_SYNTHESIZER.md](JOIN_SYNTHESIZER.md)**: Detailed SQL generation architecture and deterministic join synthesis
- **[domain_specific_guidance/README.md](domain_specific_guidance/README.md)**: Configuration guide for domain-specific customization
- **[CLAUDE.md](CLAUDE.md)**: Developer guide and project overview for AI assistants

### Key Concepts

- **Deterministic Join Synthesizer**: SQLGlot-based SQL generation without LLM calls
- **Schema Filtering**: Vector search to reduce context and improve accuracy
- **Plan Auditing**: Automatic validation and fixing of common planner mistakes
- **Conversational Flow**: Stateful query refinement through follow-up questions
- **Planner Complexity Tiers**: Optimized prompts for different model sizes

---

## Troubleshooting

### Common Issues

**Issue**: SQL Server connection errors
- **Solution**: Verify ODBC Driver 17 is installed and DB_SERVER/credentials are correct

**Issue**: OpenAI API errors
- **Solution**: Check OPENAI_API_KEY is valid and has sufficient credits

**Issue**: Ollama model not found
- **Solution**: Run `ollama pull <model-name>` first, verify with `ollama list`

**Issue**: Planner generates invalid queries
- **Solution**: Try increasing PLANNER_COMPLEXITY or using a larger model

**Issue**: Queries return no results
- **Solution**: Check domain-specific guidance is configured, review filtered schema in logs

**Issue**: Reserved keyword errors (Index, Order, etc.)
- **Solution**: This should be automatic - check SQLGlot version is up to date

---

## Contributing

### Development Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Run tests: `pytest`

### Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Add docstrings to functions
- Run flake8: `flake8 . --max-line-length=120`

### Testing

- Write unit tests for new features
- Ensure all tests pass before submitting PR
- Test with both OpenAI and Ollama models

---

## License

[Your License Here]

---

## Acknowledgments

Built with:
- **LangGraph**: Workflow orchestration
- **LangChain**: LLM framework
- **OpenAI**: Language models
- **Ollama**: Local model runtime
- **SQLGlot**: SQL parsing and generation
- **Streamlit**: Web interface
- **FastAPI**: REST API framework
- **Pydantic**: Data validation
