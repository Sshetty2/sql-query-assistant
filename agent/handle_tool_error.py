"""Handle errors from query execution by having LLM analyze and suggest fixes."""

import os
import json
from dotenv import load_dotenv
from textwrap import dedent
from langchain_core.messages import AIMessage
from models.history import ErrorCorrectionHistory
from utils.llm_factory import get_chat_llm, get_model_for_stage
from utils.logger import get_logger, log_execution_time
from utils.stream_utils import emit_node_status
from utils.debug_utils import append_to_debug_array

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
    correction_history: list[str],
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
        correction_history: List of previous errors
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
        # Fix SQL Error - Generate Corrected Strategy

        ## What Happened
        User asked: "{user_question}"
        SQL query failed with error: {error_message}

        ## Your Task
        Generate a CORRECTED STRATEGY that fixes this error. Your strategy will go directly to the planner.

        ## STEP-BY-STEP WORKFLOW (Follow exactly in this order)

        ### STEP 1: Identify What Went Wrong
        Analyze the error message. Common issues:
        - "Invalid column name 'X'" → Column doesn't exist in that table
        - "Multi-part identifier 'tb_Table.Column' not bound" → Table not joined yet or column doesn't exist
        - "Invalid object name 'tb_Table'" → Table doesn't exist in schema

        ### STEP 2: List Available Columns for Each Table
        **Before suggesting ANY join, list out the actual columns available in each table you want to use.**

        For each table mentioned in the error or needed for the query:
        1. Find it in the schema below
        2. Write out its ACTUAL columns (copy from schema)
        3. Check Foreign Keys section for join relationships

        **Available Tables:** {tables_list}

        **Database Schema:**
        ```{schema_format}
        {schema_text}
        ```

        ### STEP 3: Construct Valid Joins
        Using ONLY the columns you listed in Step 2:
        - Match Foreign Key columns to Primary Keys (usually "ID")
        - Example: tb_SaasComputers.CompanyID → tb_Company.ID
        - NEVER use columns that don't exist in the table

        ### STEP 4: Generate Corrected Strategy
        Write the complete strategy with:
        - **Tables**: Which tables to use
        - **Columns**: Which columns to select (verify they exist!)
        - **Joins**: Using actual FK relationships
        - **Filters**: Any WHERE conditions
        - **Aggregations**: GROUP BY if needed
        - **Ordering**: ORDER BY if needed
        - **Limiting**: Result limit if needed

        ## CRITICAL RULES
        1. ⚠️ ONLY use tables from "Available Tables" list above
        2. ⚠️ ONLY use columns that ACTUALLY EXIST in the table (check schema!)
        3. ⚠️ For joins, use Foreign Key relationships from schema
        4. ⚠️ Most table PKs are named "ID" (not TableNameID)
        5. ⚠️ Preserve the user's intent - just fix the technical errors

        ## OUTPUT
        Write ONLY the corrected strategy in markdown format (no explanation, no preamble).
        Use the same sections as this previous strategy:

        ```
        {original_strategy}
        ```
    """
    ).strip()

    try:
        # Use higher temperature for error correction to encourage different approaches
        error_correction_model = get_model_for_stage("error_correction")
        llm = get_chat_llm(model_name=error_correction_model, temperature=0.5)

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
    user_question = state.get("user_question", "")
    error_iteration = state.get("error_iteration", 0)

    # Get max error correction attempts from environment
    max_error_corrections = (
        int(os.getenv("ERROR_CORRECTION_COUNT"))
        if os.getenv("ERROR_CORRECTION_COUNT")
        else 3
    )

    logger.info(
        "Starting plan correction for error",
        extra={
            "error_iteration": error_iteration,
            "error": error_message,
            "original_query": original_query,
        },
    )

    # Use truncated schema if available (preferred for LLM context), otherwise filtered
    schema = (
        state.get("truncated_schema") or state.get("filtered_schema") or state["schema"]
    )

    # Get previous error messages from correction_history
    correction_history = state.get("correction_history", [])

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
    if error_iteration > max_error_corrections:
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
        correction_history=correction_history,
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

    # Create structured error correction history object
    correction_record = ErrorCorrectionHistory(
        strategy=revised_strategy,
        plan=original_plan_dict,
        query=original_query,
        reasoning=f"SQL execution error encountered: {error_message}. "
        f"Generated revised strategy to fix the error.",
        error=error_message,
        iteration=error_iteration + 1,
    )

    # Debug: Append to single error correction history array

    append_to_debug_array(
        "error_correction_history.json",
        {
            **correction_record.model_dump(),
            "previous_strategy": previous_strategy,
            "fk_fixes_applied": fk_fixes,
        },
        step_name="handle_tool_error",
        array_key="corrections",
    )

    emit_node_status("handle_tool_error", "completed")

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
        "correction_history": state.get("correction_history", [])
        + [correction_record.model_dump()],
        "last_step": "handle_tool_error",
    }
