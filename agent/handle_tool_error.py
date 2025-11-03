"""Handle errors from query execution by having LLM analyze and suggest fixes."""

import os
import json
from dotenv import load_dotenv
from textwrap import dedent
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from models.planner_output import PlannerOutput
from utils.llm_factory import get_chat_llm
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()

# Maximum number of retries for output parsing errors
MAX_ERROR_CORRECTION_RETRIES = 2


def extract_validation_error_details(error_message: str) -> str:
    """
    Extract readable validation error details from Pydantic validation error.

    Args:
        error_message: The error message from OutputParserException

    Returns:
        Human-readable error description
    """
    import re

    # Extract validation error type and details
    if "join_edges reference tables not" in error_message:
        # Extract missing tables using regex
        match = re.search(r"\['([^']+)'(?:,\s*'([^']+)')*\]", error_message)
        if match:
            missing_tables = [g for g in match.groups() if g]
            return f"Tables referenced in join_edges but not in selections: {', '.join(missing_tables)}"

    # Generic fallback
    return f"Validation error: {error_message}"


class ErrorCorrection(BaseModel):
    """Pydantic model for error correction output (legacy - used for feedback generation)."""

    reasoning: str = Field(
        description="Explanation of what caused the error and how the plan was corrected"
    )
    corrected_plan: PlannerOutput = Field(
        description="The corrected query plan with fixes applied"
    )


def validate_strategy_tables(
    strategy: str, schema: list[dict]
) -> tuple[bool, list[str], list[str]]:
    """
    Validate that all tables mentioned in strategy exist in schema.

    Args:
        strategy: The strategy text to validate
        schema: Database schema

    Returns:
        (is_valid, valid_tables, invalid_tables)
    """
    import re

    # Extract available table names from schema
    available_tables = {
        table.get("table_name") for table in schema if table.get("table_name")
    }

    # Find all table references in strategy (pattern: tb_TableName or `tb_TableName`)
    table_pattern = r'(?:^|\s|`|\'|"|\(|\[)+(tb_[A-Za-z0-9_]+)'
    found_tables = set(re.findall(table_pattern, strategy))

    # Separate valid and invalid tables
    valid_tables = [t for t in found_tables if t in available_tables]
    invalid_tables = [t for t in found_tables if t not in available_tables]

    is_valid = len(invalid_tables) == 0

    return is_valid, valid_tables, invalid_tables


def generate_revised_strategy(
    error_message: str,
    original_query: str,
    original_strategy: str,
    user_question: str,
    error_history: list[str],
    schema: list[dict],
    schema_markdown: str = None,
) -> str:
    """
    Generate a revised strategy directly from SQL execution error.

    Bypasses pre-planner and generates a corrected strategy that fixes the error.
    The revised strategy will be sent directly to planner for JSON conversion.

    Args:
        error_message: The SQL error message
        original_query: The SQL query that failed
        original_strategy: The previous strategy text that led to the error
        user_question: The original user question
        error_history: List of previous errors
        schema: The database schema (filtered/truncated) as list of dicts
        schema_markdown: The database schema formatted as markdown (easier to search)

    Returns:
        Revised strategy text (will be sent to planner)
    """
    # Use markdown schema if available (easier to search), otherwise JSON
    if schema_markdown:
        schema_text = schema_markdown
        schema_format = "markdown"
    else:
        schema_text = json.dumps(schema, indent=2)
        schema_format = "json"

    # Extract available table names from schema
    available_tables = [
        table.get("table_name") for table in schema if table.get("table_name")
    ]
    tables_list = "\n".join([f"- {table}" for table in available_tables])

    prompt = dedent(
        f"""
        # Generate Revised Strategy from SQL Error

        ## System Overview

        We're building a SQL query assistant that converts natural language to SQL queries.
        The system uses a **two-stage planning approach**:

        1. **Pre-Planner** (stage 1) - Creates a text-based strategic plan for NEW queries
        2. **Planner** (stage 2) - Converts strategy to structured JSON
        3. **SQL Generator** - Deterministically converts JSON to SQL

        **Your Role:** You're the **error correction strategist**. A query was executed and failed with a
        SQL error. Generate a REVISED STRATEGY that fixes the error. Your output will go DIRECTLY to the
        planner (skip pre-planner).

        **Important:** Generate a COMPLETE revised strategy in the same format as the original strategy below.
        This is NOT feedback - this IS the corrected strategy that will be converted to JSON.

        ---

        ## User's Original Question
        ```
        {user_question}
        ```

        ## Previous Strategy GENERATED BY PRE-PLANNER LLM AGENT (Contains Errors)
        ```
        {original_strategy}
        ```

        ## SQL Error
        ```
        {error_message}
        ```

        ## ⚠️ AVAILABLE TABLES IN DATABASE SCHEMA ⚠️

        **CRITICAL: You MUST ONLY use tables from this list.**
        **DO NOT invent or hallucinate table names!**

        {tables_list}

        **If the error mentions a table that is NOT in this list, you MUST:**
        - Remove that table from your strategy
        - Find an alternative table from the list above that serves a similar purpose
        - Or restructure the query to work without that table

        ---

        ## Database Schema (Reference for Corrections)
        ```{schema_format}
        {schema_text}
        ```
        ---

        ## Your Task

        Generate a REVISED STRATEGY that fixes the SQL error. Use the EXACT format of the original strategy above.

        **Critical Requirements:**

        0. **VERIFY table ownership for EVERY column** (TOP PRIORITY):
           a) Before using ANY column, find it in the schema above
           b) Note which SPECIFIC table contains that column
           c) Use the EXACT table.column reference from schema
           d) Common mistake: Assuming columns are in the "main" table
           e) Reality: Check detail tables (tables with suffixes like "Details", "Map", "Info")

           **Example Process:**
           - Error: "Invalid column name 'SomeColumn' in tb_MainTable"
           - Step 1: Search schema above for "SomeColumn"
           - Step 2: Find which table actually contains "SomeColumn" (check ALL tables, not just tb_MainTable)
           - Step 3: If found in tb_DetailTable (NOT tb_MainTable!), use tb_DetailTable.SomeColumn instead
           - Step 4: If tb_DetailTable is not in the filtered schema above, DO NOT use it. Find an alternative.
           - Step 5: Add necessary join: tb_MainTable.ID = tb_DetailTable.ForeignKeyID

           **CRITICAL:** Only use tables that appear in the "AVAILABLE TABLES" list above!

        1. **VERIFY tables exist FIRST**: Before planning anything, check that ALL tables you want to use
           are in the "Available Tables" list above. DO NOT use any table not in that list.

        2. **Address ALL errors**: The SQL error may contain multiple issues. Fix EVERY error mentioned.

        3. **VERIFY columns exist**: Before using ANY column, you MUST:
           a) Find the table in the schema above
           b) Check the table's actual columns
           c) Confirm the column EXISTS in that list
           d) If the column doesn't exist, use a similar column that DOES exist

        4. **CRITICAL: Foreign Key Resolution**:
           a) If error mentions column like "tb_TableX.ColumnNameID could not be bound"
           b) Check if ColumnNameID exists in tb_TableX columns list
           c) If NOT found, look for "Foreign Keys" section in tb_TableX
           d) Find the FK definition (e.g., "ColumnNameID → tb_OtherTable.ID")
           e) Use EXACT column names from FK definition in your join

           **Example:**
           - Error: "tb_SaasScan.ScanID could not be bound"
           - Check tb_SaasScan columns: NO ScanID column found
           - Check Foreign Keys in tb_SaasComputers: "ScanID → tb_SaasScan.ID"
           - CORRECT join: tb_SaasScan.ID = tb_SaasComputers.ScanID
           - WRONG join: tb_SaasScan.ScanID = tb_SaasComputers.ScanID ❌

        5. **Table Primary Keys are always "ID"**:
           - Most tables have PK named "ID" (not TableNameID)
           - Foreign keys in OTHER tables reference this "ID" column
           - Example: tb_Company.ID ← tb_SaasComputers.CompanyID

        6. **Verify joins step-by-step**:
           a) Identify which table is not joined
           b) Find the FK relationship in the "Foreign Keys" section
           c) Use the EXACT columns from the FK definition
           d) Double-check both columns exist in their respective tables

        7. **ZERO tolerance for hallucinations**:
           - NEVER use a table that is not in the "Available Tables" list
           - NEVER use a column that doesn't appear in the schema

        8. **Preserve user intent**: Don't change WHAT the user asked for, only fix HOW to get it.

        9. **Keep same format**: Use the same markdown structure, headings, and sections as the original strategy.

        **Common SQL Error Fixes:**
        - "Invalid column name 'X'" → Find the correct column name in the schema and use it
        - "Multi-part identifier 'tb_Table.Column' not bound" → Add join for tb_Table
        - "Invalid object name 'tb_Table'" → Use a table that exists in schema
        - Type conversion errors → Fix join columns to use compatible types
        - Foreign key mismatch → Use correct FK columns from schema

        **Output Format:**
        Generate a complete revised strategy in markdown format with these sections:
        - **Tables**: List of tables needed
        - **Columns**: List of columns to select/filter
        - **Joins**: How tables connect (use FK relationships from schema)
        - **Filters**: Conditions to apply
        - **Aggregations**: Any grouping/aggregation needed
        - **Ordering**: How to sort results
        - **Limiting**: Result limit

        **IMPORTANT:**
        - Output ONLY the revised strategy text (no preamble, no "here's the strategy")
        - Use the same format as the original strategy above
        - Verify ALL columns exist in the schema before including them
    """
    ).strip()

    try:
        llm = get_chat_llm(model_name=os.getenv("AI_MODEL"))

        with log_execution_time(logger, "llm_revised_strategy_generation"):
            result = llm.invoke(prompt)

        # Extract text content from LangChain message
        revised_strategy = result.content if hasattr(result, "content") else str(result)
        revised_strategy = revised_strategy.strip()

        # CRITICAL: Validate that LLM didn't hallucinate table names
        is_valid, valid_tables, invalid_tables = validate_strategy_tables(
            revised_strategy, schema
        )

        if not is_valid:
            logger.error(
                f"LLM hallucinated {len(invalid_tables)} non-existent tables in revised strategy!",
                extra={
                    "invalid_tables": invalid_tables,
                    "valid_tables": valid_tables,
                    "available_tables": [t.get("table_name") for t in schema],
                },
            )

            # Add validation warning to strategy
            invalid_tables_list = "\n".join(["- " + t for t in invalid_tables])
            available_tables_list = "\n".join(
                ["- " + t.get("table_name") for t in schema if t.get("table_name")]
            )

            warning = dedent(
                f"""

                ⚠️ **VALIDATION ERROR DETECTED** ⚠️
                The revised strategy references tables that DO NOT EXIST in the schema:
                {invalid_tables_list}

                Available tables in schema:
                {available_tables_list}

                **ACTION REQUIRED:** Remove or replace non-existent tables before proceeding.
            """
            ).strip()

            revised_strategy = revised_strategy + "\n\n" + warning

        else:
            logger.info(
                f"Revised strategy validated successfully - all {len(valid_tables)} tables exist in schema",
                extra={"tables": valid_tables},
            )

        return revised_strategy

    except Exception as e:
        logger.error(f"Error generating revised strategy: {str(e)}", exc_info=True)

        # Fallback: Return original strategy with error note
        error_note = dedent(
            f"""
            {original_strategy}

            ---

            **ERROR CORRECTION NOTE:**
            Failed to generate revised strategy due to: {str(e)}
            SQL Error: {error_message}
            Please review schema and ensure correct table/column names are used.
        """
        ).strip()

        return error_note


def handle_tool_error(state) -> dict:
    """Handle errors from query execution by correcting the plan."""
    error_message = state["messages"][-1].content
    original_query = state["query"]
    original_plan = state["planner_output"]
    retry_count = state.get("retry_count", 0)
    user_question = state.get("user_question", "")

    # Get max error correction attempts from environment
    max_error_corrections = (
        int(os.getenv("ERROR_CORRECTION_COUNT"))
        if os.getenv("ERROR_CORRECTION_COUNT")
        else 3
    )

    logger.info(
        "Starting plan correction for error",
        extra={
            "retry_count": retry_count,
            "error": error_message,
            "original_query": original_query,
        },
    )

    # Use truncated schema if available (preferred for LLM context), otherwise filtered
    schema = (
        state.get("truncated_schema") or state.get("filtered_schema") or state["schema"]
    )
    error_history = state["error_history"][:-1]
    error_iteration = state.get("error_iteration", 0)

    # Get the strategy that led to the error (could be from pre-planner or previous revision)
    previous_strategy = state.get("revised_strategy") or state.get(
        "pre_plan_strategy", ""
    )

    # Format the original plan for history tracking
    if hasattr(original_plan, "model_dump"):
        original_plan_dict = original_plan.model_dump()
    else:
        original_plan_dict = original_plan

    logger.warning(
        f"SQL execution error (iteration {error_iteration + 1}/{max_error_corrections})",
        extra={"error": error_message, "error_iteration": error_iteration},
    )

    # Check if we've exhausted iteration limit
    if error_iteration >= max_error_corrections:
        logger.error(
            f"Error iteration limit reached ({max_error_corrections} iterations), terminating",
            extra={"error": error_message},
        )
        return {
            **state,
            "messages": [
                AIMessage(
                    content=f"SQL error after {error_iteration} correction attempts"
                )
            ],
            "planner_output": original_plan_dict,
            "needs_termination": True,
            "termination_reason": f"SQL execution error: {error_message}",
            "corrected_plans": state["corrected_plans"] + [original_plan_dict],
            "error_reasoning": state.get("error_reasoning", [])
            + [f"⚠️ ERROR: {error_message}"],
            "last_step": "handle_tool_error",
        }

    # Generate revised strategy directly (bypasses pre-planner)
    # Use markdown schema if available (easier for LLM to search)
    schema_markdown = state.get("schema_markdown", None)

    revised_strategy = generate_revised_strategy(
        error_message=error_message,
        original_query=original_query,
        original_strategy=previous_strategy,
        user_question=user_question,
        error_history=error_history,
        schema=schema,
        schema_markdown=schema_markdown,
    )

    logger.info(
        "Generated revised strategy (bypassing pre-planner)",
        extra={
            "strategy_length": len(revised_strategy),
            "error_iteration": error_iteration + 1,
        },
    )

    # Apply deterministic FK join validation and fixes
    from agent.validate_fk_joins import validate_and_fix_strategy_joins

    revised_strategy, fk_fixes = validate_and_fix_strategy_joins(
        revised_strategy, schema
    )

    if fk_fixes:
        logger.info(
            f"Applied {len(fk_fixes)} deterministic FK fixes to revised strategy",
            extra={"fixes": fk_fixes, "error_iteration": error_iteration + 1},
        )
    else:
        logger.debug("No FK fixes needed in revised strategy")

    # Debug: Save revised strategy
    from utils.debug_utils import save_debug_file

    save_debug_file(
        f"revised_strategy_error_iteration_{error_iteration + 1}.json",
        {
            "iteration": error_iteration + 1,
            "error": error_message,
            "revised_strategy": revised_strategy,
            "original_query": original_query,
            "previous_strategy": previous_strategy,
            "fk_fixes_applied": fk_fixes,
        },
        step_name="handle_tool_error",
    )

    # Debug: Track SQL queries during error correction
    from utils.debug_utils import append_to_debug_array

    append_to_debug_array(
        "generated_sql_queries.json",
        {
            "step": "error_correction",
            "attempt": error_iteration + 1,
            "sql": original_query,
            "error": error_message,
            "status": "failed",
        },
        step_name="handle_tool_error",
        array_key="queries",
    )

    return {
        **state,
        "messages": [
            AIMessage(
                content=f"SQL error encountered, routing to planner with revised strategy "
                f"(attempt {error_iteration + 1}/{max_error_corrections})"
            )
        ],
        "planner_output": original_plan_dict,  # Keep current plan for history
        "revised_strategy": revised_strategy,  # Revised strategy for planner
        "error_iteration": error_iteration + 1,  # Increment counter
        "corrected_plans": state["corrected_plans"] + [original_plan_dict],
        "corrected_queries": state.get("corrected_queries", [])
        + [original_query],  # Track failed query
        "error_reasoning": state.get("error_reasoning", [])
        + [f"SQL Error: {error_message}"],
        "last_step": "handle_tool_error",
    }
