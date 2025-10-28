# FK Inferencing Agent

Interactive foreign key mapping generator with human-in-the-loop verification.

## Overview

This agent helps identify potential foreign key relationships in databases without explicit FK constraints. It uses vector similarity search to find candidate tables and requires human input when ambiguous.

## Features

- **Vector Similarity Search**: Finds top-k candidate tables using semantic matching
- **Smart Auto-Selection**: Automatically selects when score gap >= threshold (default: 0.10)
- **Human-in-the-Loop**: Interrupts workflow for ambiguous cases requiring user decision
- **Excel Audit Trail**: Records all ID columns, candidates, scores, and decisions
- **Resume Capability**: Can pause (Ctrl+C) and resume from where you left off
- **Existing FK Handling**: Includes explicit FKs in audit marked as "existing"

## Installation

The agent is already part of the project. Required dependency:

```bash
pip install openpyxl
```

## Usage

### Basic Usage

```bash
python -m fk_inferencing_agent.cli
```

This uses the database specified in `.env` (DB_NAME).

### With Options

```bash
# Specify database
python -m fk_inferencing_agent.cli --database mydb

# Adjust threshold (lower = more interrupts)
python -m fk_inferencing_agent.cli --threshold 0.15

# Change number of candidates
python -m fk_inferencing_agent.cli --top-k 10
```

### Interactive Prompts

When the agent encounters an ambiguous FK mapping, it will prompt:

```
[!] AMBIGUOUS - Please choose:
  [1-5] Select candidate
  [s]   Skip this FK
  [q]   Quit and save

Your choice: _
```

- **1-5**: Select the corresponding candidate table
- **s**: Skip this FK relationship (marked as [SKIPPED])
- **q**: Quit and save progress (can resume later)

## Output

The agent creates an Excel file named `fk_mappings_{database}.xlsx` with:

- **table_name**: Source table
- **fk_column**: ID column that may be a foreign key
- **base_name**: Base name extracted from column (e.g., "user_" from "user_id")
- **candidate_1 to candidate_5**: Top 5 candidate tables
- **score_1 to score_5**: Similarity scores for each candidate
- **chosen_table**: Selected table (auto or manual)
- **chosen_score**: Score of chosen table
- **decision_type**: auto | manual | existing | skipped
- **timestamp**: When decision was made
- **notes**: Additional context (e.g., "User selected option 2")

## Architecture

The agent is built using **LangGraph** with the following workflow:

```
START
  → initialize (introspect DB, create Excel, prepare schema)
  → load_next_row (find first incomplete row)
  → find_candidates (vector search for top-k tables)
  → evaluate_ambiguity (calculate score gap)
  → [auto_select OR request_decision] (based on threshold)
  → record_decision (write to Excel)
  → [loop back to load_next_row OR finalize]
  → END
```

### Key Components

- **State**: TypedDict tracking workflow state (FKInferencingState)
- **Excel Manager**: Utilities for creating/reading/writing Excel audit trail
- **Workflow Nodes**: 8 specialized nodes for each step
- **LangGraph Interrupts**: Pauses workflow for human input
- **MemorySaver Checkpointer**: Enables resume capability

### Files

```
fk_inferencing_agent/
├── __init__.py                    # Module init
├── state.py                       # State TypedDict definition
├── excel_manager.py               # Excel I/O utilities
├── create_agent.py                # LangGraph workflow definition
├── cli.py                         # CLI entry point
└── nodes/
    ├── initialize.py              # Introspect DB, prepare schema
    ├── load_next_row.py           # Find next incomplete row
    ├── find_candidates.py         # Vector search for candidates
    ├── evaluate_ambiguity.py      # Calculate score gap
    ├── auto_select.py             # Auto-select when clear
    ├── request_decision.py        # Interrupt for human input
    ├── record_decision.py         # Write decision to Excel
    └── finalize.py                # Print summary statistics
```

## Configuration

### Environment Variables

The agent uses the following from `.env`:

- `DB_SERVER`: SQL Server hostname
- `DB_NAME`: Database name
- `DB_USER`: Database username
- `DB_PASSWORD`: Database password
- `EMBEDDING_MODEL`: Embedding model for vector search (default: text-embedding-3-small)
- `OPENAI_API_KEY`: OpenAI API key (for embeddings)

### Threshold

The threshold determines when auto-selection occurs:

- **0.05**: Very conservative, more interrupts
- **0.10**: Balanced (default)
- **0.15**: Aggressive, fewer interrupts

Score gap = (top_score - second_score). If gap >= threshold, auto-select.

## Tips

1. **Start with default threshold (0.10)**: Adjust based on your database's schema complexity
2. **Use 'q' to quit anytime**: Progress is saved, resume later
3. **Use 's' for uncertain cases**: Better to skip than select incorrectly
4. **Check Excel after completion**: Review decisions and adjust if needed
5. **Resume interrupted sessions**: Just run the command again, it will pick up where you left off

## Example Session

```bash
$ python -m fk_inferencing_agent.cli

============================================================
FK INFERENCING AGENT
============================================================
Database:  saasdb
Threshold: 0.10
Top-K:     5
============================================================

[Step 1] Connecting to database: saasdb
[PASS] Introspected 56 tables

[Step 2] Detecting ID columns...
[PASS] Found 171 ID columns

[Step 3] Creating Excel audit file...
[PASS] Created Excel: fk_mappings_saasdb.xlsx (171 ID columns)

[Step 4] Schema ready for vector search (vector store will be built on-demand)

[PASS] Initialization complete


============================================================
Processing: tb_Users.company_id
Base name: company_
============================================================

Top 5 Candidates:
  [1] tb_Company                     (score: 0.876)
  [2] tb_CompanySettings             (score: 0.623)
  [3] tb_CompanyUsers                (score: 0.601)
  [4] tb_Vendors                     (score: 0.445)
  [5] tb_Projects                    (score: 0.398)

Score gap: 0.253 (>= 0.1 threshold)
[PASS] Auto-selected: tb_Company

============================================================
Processing: tb_Logins.user_id
Base name: user_
============================================================

Top 5 Candidates:
  [1] tb_Users                       (score: 0.923)
  [2] tb_UserRoles                   (score: 0.867)
  [3] tb_UserSettings                (score: 0.823)
  [4] tb_Sessions                    (score: 0.556)
  [5] tb_Audit                       (score: 0.501)

Score gap: 0.056 (< 0.1 threshold)

[!] AMBIGUOUS - Please choose:
  [1-5] Select candidate
  [s]   Skip this FK
  [q]   Quit and save

Your choice: 1
[PASS] User selected: tb_Users

...

============================================================
FK INFERENCING SUMMARY
============================================================
Total ID columns:  171
Auto-selected:     89
Manual selection:  67
Existing FKs:      12
Skipped:           3
Incomplete:        0

Excel file: fk_mappings_saasdb.xlsx

[PASS] FK inferencing complete!
```

## Testing

A test script is available for automated testing:

```bash
python test_fk_agent.py
```

This simulates user input for the first 3 interrupts, useful for development and CI.

## Troubleshooting

### "Type is not msgpack serializable: InMemoryVectorStore"

This error indicates the vector store is being stored in state. The agent has been designed to rebuild the vector store on-demand to avoid this issue. If you see this error, ensure you're using the latest version of the code.

### "UnicodeEncodeError: 'charmap' codec can't encode characters"

This can occur on Windows terminals with limited Unicode support. The code has been updated to use ASCII characters instead of emojis.

### Excel file shows wrong data in columns

Ensure you're using the latest version of `excel_manager.py`. The column indices were corrected to properly align with the 18-column format.

## Future Enhancements

Potential improvements for future versions:

- Export to SQL ALTER TABLE statements for creating actual FK constraints
- Confidence scores based on data sampling (not just schema)
- Batch mode with configurable auto-approve threshold
- Integration with domain-specific guidance system
- Web UI for easier interaction
- Multi-database comparison
