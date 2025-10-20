# Conversational Flow Documentation

This document explains how to use the new conversational flow feature for the SQL Query Assistant.

## Overview

The conversational flow feature allows the workflow to be invoked multiple times, with each invocation building on the previous execution. This enables users to refine queries, add filters, or completely change their request without starting from scratch.

## Architecture

### Key Components

1. **State Management** (`agent/state.py`)
   - Tracks conversation history with `user_questions` list
   - Stores query history in `queries` list
   - Maintains planner output history in `planner_outputs` list
   - Uses `is_continuation` flag to route between initial and continuation flows

2. **Conversational Router** (`agent/conversational_router.py`)
   - Analyzes follow-up requests in context of conversation history
   - Decides how to handle changes:
     - **revise_query_inline**: For small SQL changes (e.g., add/remove column)
     - **update_plan**: For minor plan modifications (e.g., add filter)
     - **rewrite_plan**: For major changes (e.g., different tables)

3. **Router Output Model** (`models/router_output.py`)
   - Structured output with decision enum
   - Optional `revised_query` for inline revisions
   - Optional `routing_instructions` for planner guidance

4. **Updated Planner** (`agent/planner.py`)
   - Three operational modes:
     - **None (initial)**: Full schema analysis for new queries
     - **update**: Incremental plan updates without full schema
     - **rewrite**: Complete replanning with full schema

5. **Workflow Graph** (`agent/create_agent.py`)
   - Conditional routing from START based on `is_continuation`
   - Router node with conditional edges to planner or execute_query
   - Maintains all existing error handling and refinement logic

## Usage

### Basic Usage (New Conversation)

```python
from agent.query_database import query_database

# Initial query
result = query_database(
    question="Show me all active users",
    sort_order="Ascending",
    result_limit=100
)

print(result["query"])  # Generated SQL
print(result["result"]) # Query results
```

### Conversational Follow-up

```python
# Follow-up query - pass previous state
result2 = query_database(
    question="Add the email column",
    previous_state=result  # Pass the previous result state
)

print(result2["query"])  # Modified SQL with email column
```

### Multiple Iterations

```python
# First query
state1 = query_database("Show me companies")

# Add filter
state2 = query_database(
    "Filter to only active companies",
    previous_state=state1
)

# Change tables completely
state3 = query_database(
    "Actually, show me products instead",
    previous_state=state2
)

# Each state contains full history
print(f"User questions: {state3['user_questions']}")
print(f"Query history: {state3['queries']}")
```

## Router Decision Logic

The conversational router uses the following guidelines:

### Revise Query Inline
- **When**: Trivial SQL modifications that don't affect the query plan
- **Examples**:
  - "Add the name column"
  - "Remove the description field"
  - "Change LIMIT to 50"
- **Workflow**: Router → Execute Query (skips planner)

### Update Plan
- **When**: Minor modifications that require plan adjustments
- **Examples**:
  - "Filter by status = 'Active'"
  - "Group by company"
  - "Sort by date descending"
  - "Add timestamp filtering"
- **Workflow**: Router → Planner (update mode) → Generate Query → Execute Query

### Rewrite Plan
- **When**: Major changes requiring complete replanning
- **Examples**:
  - "Show me products instead of users"
  - "Now query the orders table"
  - "I want to see CVE data instead"
  - "Change to a completely different domain"
- **Workflow**: Router → Planner (rewrite mode) → Generate Query → Execute Query

## State Structure

Key state fields for conversational flow:

```python
{
    # Conversation tracking
    "user_questions": ["query 1", "query 2", ...],  # Full history
    "user_question": "latest query",                 # Current question
    "is_continuation": True/False,                   # Routing flag

    # Query history
    "queries": ["SELECT ...", "SELECT ...", ...],   # All SQL queries
    "query": "SELECT ...",                           # Current SQL

    # Planning history
    "planner_outputs": [{...}, {...}, ...],         # All plans
    "planner_output": {...},                        # Current plan

    # Router state
    "router_mode": "update" | "rewrite" | None,
    "router_instructions": "Add filter on...",

    # Schema and results
    "schema": [...],                                 # Database schema
    "result": "...",                                 # Query results

    # Other fields (error handling, preferences, etc.)
    ...
}
```

## Integration with Streamlit/FastAPI

### Streamlit Integration

To use in Streamlit, store state in session:

```python
import streamlit as st
from agent.query_database import query_database

# Initialize session state
if 'conversation_state' not in st.session_state:
    st.session_state.conversation_state = None

# User input
question = st.text_input("Ask a question:")

if st.button("Submit"):
    # Pass previous state if exists
    result = query_database(
        question=question,
        previous_state=st.session_state.conversation_state
    )

    # Store for next iteration
    st.session_state.conversation_state = result

    # Display results
    st.write(result["result"])

# Clear conversation button
if st.button("New Conversation"):
    st.session_state.conversation_state = None
```

### FastAPI Integration

To use in FastAPI, maintain conversation state per session:

```python
from fastapi import FastAPI, Depends
from typing import Optional, Dict, Any

app = FastAPI()

# In-memory session store (use Redis/database in production)
conversation_sessions = {}

@app.post("/query")
async def query(
    question: str,
    session_id: Optional[str] = None
):
    previous_state = None

    # Get previous state if session exists
    if session_id and session_id in conversation_sessions:
        previous_state = conversation_sessions[session_id]

    # Execute query
    result = query_database(
        question=question,
        previous_state=previous_state
    )

    # Store state for session
    if session_id:
        conversation_sessions[session_id] = result

    return {
        "query": result["query"],
        "result": result["result"],
        "session_id": session_id
    }

@app.post("/clear_session")
async def clear_session(session_id: str):
    if session_id in conversation_sessions:
        del conversation_sessions[session_id]
    return {"status": "cleared"}
```

## Testing

Example test scenarios:

```python
# Test 1: Simple follow-up
state1 = query_database("Show companies")
state2 = query_database("Add vendor column", previous_state=state1)
assert "vendor" in state2["query"].lower()

# Test 2: Filter addition
state1 = query_database("Show all users")
state2 = query_database("Only active ones", previous_state=state1)
assert "active" in state2["query"].lower()

# Test 3: Complete change
state1 = query_database("Show companies")
state2 = query_database("Show products instead", previous_state=state1)
assert "product" in state2["query"].lower()
assert len(state2["user_questions"]) == 2
```

## Best Practices

1. **Always pass the full state**: Don't cherry-pick fields - pass the entire result dictionary as `previous_state`

2. **Handle state persistence**: In production apps, serialize and store state in sessions/database

3. **Clear conversations when needed**: Provide users with a way to start fresh conversations

4. **Monitor token usage**: Long conversations accumulate history - consider truncating after N iterations

5. **Error handling**: If router fails, fall back to initial workflow by not passing `previous_state`

## Troubleshooting

### Router always chooses rewrite
- Check if schema is too different between requests
- Verify conversation history is being passed correctly

### Planner doesn't use previous plan
- Ensure `router_mode` is set correctly in state
- Check `planner_outputs` list contains previous plans

### Query history not accumulating
- Verify `execute_query` is appending to `queries` list
- Check state is being passed between invocations

### State getting too large
- Implement state truncation after N iterations
- Store only essential history (last 5 queries, etc.)

## Future Enhancements

Potential improvements to consider:

1. **Smart context pruning**: Automatically remove old queries when context gets too large
2. **Conversation branching**: Support multiple conversation threads
3. **State serialization helpers**: Utilities for saving/loading state
4. **Conversation summaries**: LLM-generated summaries of long conversations
5. **Rollback support**: Ability to revert to previous states
