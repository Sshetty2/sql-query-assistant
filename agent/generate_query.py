"""Generate a SQL query based on the question and schema."""

import os
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from agent.state import State

load_dotenv()


def get_database_context():
    """Get database-specific context."""
    is_test_db = os.getenv("USE_TEST_DB", "").lower() == "true"
    return {
        "type": "SQLite" if is_test_db else "SQL Server",
        "is_sqlite": is_test_db,
        "is_sql_server": not is_test_db,
    }


def create_sql_generation_prompt():
    """Create the prompt template for SQL generation."""

    system_message = """You are translating a structured query execution plan into executable SQL.

## Context

You are part of a multi-step SQL generation pipeline. A previous step analyzed the user's request
and database schema to create a detailed execution plan. Your job is to translate that plan into
correct, efficient SQL.

The plan specifies:
- Which tables to query
- Which columns to select, filter, group, or order
- How tables are related (via join hints)
- What conditions to apply
- Time-based filters if applicable

## Database: {db_type}

{db_specific_notes}

## Output Requirements

Return ONLY the SQL query - no explanations, no markdown code blocks, no extra text.

Example of correct output:
SELECT * FROM users WHERE active = 1

Example of incorrect output:
```sql
SELECT * FROM users WHERE active = 1
```

## SQL Best Practices

- Use explicit JOIN syntax (INNER JOIN, LEFT JOIN, etc.)
- Include table aliases for readability when joining multiple tables
- Reference columns with table names/aliases (e.g., u.user_id not just user_id)
- Apply filters in WHERE clause before GROUP BY when possible
- Use appropriate NULL handling (IS NULL, IS NOT NULL, COALESCE)
- For text filters, consider case sensitivity requirements"""

    user_message = """## Original User Request
{user_question}

## Execution Plan
{plan}

## Implementation Notes
{notes}

Generate the SQL query that implements this plan."""

    return ChatPromptTemplate.from_messages(
        [("system", system_message), ("user", user_message)]
    )


def generate_query(state: State):
    """Generate SQL query based on the planner output and schema."""
    try:
        question = state["user_question"]
        planner_output = state.get("planner_output")

        # Debug: Dump planner output to JSON file
        if isinstance(planner_output, dict):
            plan_dict = planner_output
        else:
            # It's a Pydantic model - use model_dump()
            plan_dict = planner_output.model_dump() if planner_output else {}

        with open("debug_planner_output.json", "w") as f:
            json.dump(plan_dict, f, indent=2)

        # If no planner output, fall back to basic query generation
        # if not planner_output:
        #     return generate_basic_query(state)

        db_context = get_database_context()

        # Database-specific notes
        db_notes = []
        if db_context["is_sqlite"]:
            db_notes.append("- Use LIMIT for result limiting")
            db_notes.append("- Date functions: date(), datetime(), julianday()")
            db_notes.append("- String matching: LIKE (case-insensitive)")
        else:  # SQL Server
            db_notes.append("- Use TOP for result limiting")
            db_notes.append("- Date functions: GETDATE(), DATEADD(), DATEDIFF()")
            db_notes.append(
                "- String matching: LIKE (case-sensitive), use LOWER() for case-insensitive"
            )

        db_specific_text = "\n".join(db_notes)

        # Extract notes from plan - FIX: the Pydantic model uses notes_for_join_planner, not notes_for_sql_generator
        plan_notes = ""
        ambiguities = []

        # Handle both Pydantic model and dict
        if isinstance(planner_output, dict):
            plan_notes = planner_output.get(
                "notes_for_join_planner"
            ) or planner_output.get("notes_for_sql_generator", "")
            ambiguities = planner_output.get("ambiguities", [])
        else:
            # It's a Pydantic model
            plan_notes = getattr(planner_output, "notes_for_join_planner", "") or ""
            ambiguities = getattr(planner_output, "ambiguities", [])

        notes_parts = []
        if plan_notes:
            notes_parts.append(f"Planner notes: {plan_notes}")
        if ambiguities:
            notes_parts.append(f"Assumptions made: {', '.join(ambiguities)}")

        notes_text = "\n".join(notes_parts) if notes_parts else "No additional notes"

        # Convert Pydantic model to dict for JSON serialization
        if isinstance(planner_output, dict):
            plan_dict = planner_output
        else:
            # It's a Pydantic model - use model_dump()
            plan_dict = planner_output.model_dump()

        # Create prompt
        prompt_template = create_sql_generation_prompt()

        formatted_prompt = prompt_template.format_messages(
            db_type=db_context["type"],
            db_specific_notes=db_specific_text,
            user_question=question,
            plan=json.dumps(plan_dict, indent=2),
            notes=notes_text,
        )

        llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.7)
        response = llm.invoke(formatted_prompt)

        query = response.content.strip()

        return {
            **state,
            "messages": [AIMessage(content="Generated SQL query from execution plan")],
            "query": query,
            "last_step": "generate_query",
        }
    except Exception as e:
        return {
            **state,
            "messages": [AIMessage(content=f"Error generating query: {str(e)}")],
            "last_step": "generate_query",
        }


# def generate_basic_query(state: State):
#     """Fallback method for basic query generation without planner output."""
#     question = state["user_question"]
#     schema = state["schema"]
#     db_context = get_database_context()

#     sort_order = state["sort_order"]
#     result_limit = state["result_limit"]
#     time_filter = state["time_filter"]

#     requirements = []
#     if sort_order != "Default":
#         requirements.append(f"- Order results {sort_order.lower()}")
#     if result_limit > 0:
#         requirements.append(f"- Limit to {result_limit} records")
#     if time_filter != "All Time":
#         requirements.append(f"- Time filter: {time_filter}")

#     requirements_text = "\n".join(requirements) if requirements else "None"

#     system_message = f"""You are generating SQL for a {db_context["type"]} database.

# Given a database schema and user question, create an appropriate SQL query.

# Output only the SQL query - no explanations, no markdown formatting."""

#     user_message = f"""## Database Schema
# {json.dumps(schema, indent=2)}

# ## User Question
# {question}

# ## Additional Requirements
# {requirements_text}

# Generate the SQL query."""

#     prompt = ChatPromptTemplate.from_messages(
#         [("system", system_message), ("user", user_message)]
#     )

#     formatted_prompt = prompt.format_messages(
#         schema=json.dumps(schema, indent=2),
#         question=question,
#         requirements_text=requirements_text,
#     )

#     llm = ChatOpenAI(model=os.getenv("AI_MODEL"), temperature=0.2)
#     response = llm.invoke(formatted_prompt)

#     query = response.content.strip()

#     return {
#         **state,
#         "messages": [AIMessage(content="Generated SQL query (fallback mode)")],
#         "query": query,
#         "last_step": "generate_query",
#     }
