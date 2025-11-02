"""Handle errors from query execution by having LLM analyze and suggest fixes."""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from textwrap import dedent
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from langchain_core.exceptions import OutputParserException
from models.planner_output import PlannerOutput
from utils.llm_factory import get_structured_llm
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
    return f"Validation error: {error_message[:200]}"


class ErrorCorrection(BaseModel):
    """Pydantic model for error correction output."""

    reasoning: str = Field(
        description="Explanation of what caused the error and how the plan was corrected"
    )
    corrected_plan: PlannerOutput = Field(
        description="The corrected query plan with fixes applied"
    )


def handle_tool_error(state) -> dict:
    """Handle errors from query execution by correcting the plan."""
    error_message = state["messages"][-1].content
    original_query = state["query"]
    original_plan = state["planner_output"]
    retry_count = state.get("retry_count", 0)
    user_question = state.get("user_question", "")

    logger.info(
        "Starting plan correction for error",
        extra={
            "retry_count": retry_count,
            "error": error_message[:200],
            "original_query": original_query[:200],
        },
    )

    # Use filtered schema if available, otherwise use full schema
    schema = state.get("filtered_schema") or state["schema"]
    error_history = state["error_history"][:-1]

    # Format the original plan for display
    # Ensure plan is a dict (in case it's a Pydantic model)
    if hasattr(original_plan, "model_dump"):
        original_plan_dict = original_plan.model_dump()
    else:
        original_plan_dict = original_plan

    original_plan_json = json.dumps(original_plan_dict, indent=2)

    # Extract helpful hints from error message for common errors
    error_hints = ""
    if "Invalid column name" in error_message:
        error_hints = """
## ⚠️ Column Name Error Detected

The error indicates one or more columns don't exist in the specified tables.

**Common Causes:**
1. **Wrong Table Reference** - Column exists but in a different table than referenced
   - Example: Referencing tb_MainTable.Status when Status is actually in tb_JoinedTable
   - Solution: Check the schema and use the correct table name where the column exists

2. **Column Name Typo** - Column name is misspelled
   - Solution: Match the exact column name from the schema (case-sensitive)

3. **Missing JOIN** - Column is in a table that wasn't joined
   - Solution: Add the table containing the column to selections and create appropriate join_edges

**Action:** Review the schema carefully and ensure all column references use the correct table name.
"""
    elif "same exposed names" in error_message or "duplicate" in error_message.lower():
        error_hints = """
## ⚠️ Duplicate Table Error Detected

The same table appears multiple times in the query without proper distinction.

**Cause:** The plan includes the same table multiple times in selections or creates redundant joins.

**Solution:**
- Remove duplicate tables from selections (keep only one instance)
- Ensure join_edges don't create redundant paths to the same table
- If you truly need the same table twice, the system doesn't support aliases yet
"""

    prompt = dedent(
        f"""
        # Error Correction Assistant

        We're building a SQL query assistant that converts natural language to SQL queries.
        A query plan was created and converted to SQL, but **the SQL failed during execution**.

        ## Your Role in the Pipeline

        You're in the error recovery step. The pipeline works like this:

        1. **Query Planning** (completed) - Created a structured plan
        2. **SQL Generation** (completed) - Converted plan to SQL deterministically
        3. **Execution** (failed) - SQL raised an error ❌
        4. **Error Correction** (your step) - Fix the plan so SQL will succeed

        ## What We Need From You

        Analyze the error and create a **corrected plan**. When this plan is converted to SQL again,
        it should execute successfully.

        ## Original Query Plan

        ```json
        {original_plan_json}
        ```

        ## Generated Query (from above plan)

        ```sql
        {original_query}
        ```

        ## Error from Execution

        ```
        {error_message}
        ```
        {error_hints}

        ## Previous Error History

        {chr(10).join(['- ' + err for err in error_history]) if error_history else 'No previous errors'}

        ## Database Schema (with column types)

        ```json
        {schema}
        ```

        ---

        ## IMPORTANT: Plan Correction Strategy

        **CRITICAL: Never Give Up!**

        > **"With great power comes great responsibility."**

        **YOU MUST USE `decision="proceed"` IN YOUR CORRECTED PLAN!**

        - **NEVER EVER use `decision="terminate"`** - This will cause the entire workflow to fail
        - If you identified tables and columns to fix → you MUST use `decision="proceed"`
        - If you created a corrected plan structure → you MUST use `decision="proceed"`
        - If you can't fix the error perfectly → simplify the query but still use `decision="proceed"`
        - Error correction is about **fixing the plan**, not giving up on the query
        - Using `decision="terminate"` will trigger a validation error and waste the correction attempt

        **Rule of thumb:** If you wrote ANY corrected `selections`, `join_edges`, or `filters`, you MUST use `decision="proceed"`.

        **First Priority - FIX COLUMN/TABLE MISMATCHES:**
        - **Invalid column errors:** Check if column exists in a different table
        - **Join errors:** Foreign keys often join to primary keys with different names
          - Example: `tb_ApplicationTagMap.TagID` joins to `tb_SoftwareTagsAndColors.ID` (not TagID!)
        - **WHERE clause errors:** Check if column is in a joined table, not the main table
        - Use the schema to find correct table and column combinations

        **Second Priority - MAINTAIN THE ORIGINAL INTENT:**

        ⚠️ **CRITICAL: DO NOT CHANGE THE USER'S ORIGINAL QUESTION!**

        The user asked a specific question. Your job is to FIX ERRORS, NOT REWRITE THE QUERY.

        **Original User Question:**
        ```
        {user_question}
        ```

        **Your corrected plan MUST answer this SAME question.**

        ❌ **FORBIDDEN:** Changing the intent to a different question
        - Example: User asks "Count CVEs by priority" → You change to "Find computers with apps" ← WRONG!
        - Example: User asks "Show companies" → You change to "Show applications" ← WRONG!

        ✅ **CORRECT:** Keep the same intent, just fix the technical errors
        - User asks "Count CVEs by priority" → Fix joins but keep counting CVEs by priority
        - User asks "Show companies" → Fix column names but keep showing companies

        **Rules:**
        - Keep the user's original question in mind ALWAYS
        - Don't remove essential columns or tables unless they're DIRECTLY causing errors
        - If unsure how to fix, simplify BUT KEEP THE SAME INTENT

        **Third Priority - Verify Schema Accuracy:**
        - Ensure all columns exist in their respective tables
        - Verify column names match exactly (check data types in schema)
        - Check that selected columns are valid
        - Use schema foreign_keys to identify correct join relationships

        **Fourth Priority - Fix Data Type Mismatches:**
        - **Check JOIN columns** - ensure joined columns have compatible data types
        - Review foreign key relationships in the schema to identify correct join columns
        - For example, if joining `tb_Users` to `tb_UserLoginInfo`, check:
          - `tb_UserLoginInfo.UserID` (bigint) should join to `tb_Users.ID` (bigint)
          - NOT `tb_Users.UserID` (nvarchar) - this would cause type conversion errors

        **Fifth Priority - Simplify if Needed:**
        - Consider simplifying complex joins if they're causing issues
        - Remove problematic filters that might be incorrect
        - Sometimes a simpler plan is better than a complex failing one

        **Additional Considerations:**
        - Review the error history to avoid repeating mistakes
        - Pay special attention to type conversion errors - these often indicate wrong join columns
        - Ensure proper SQL Server T-SQL syntax compatibility

        **IMPORTANT: Preserve ORDER BY and LIMIT**
        - If the original plan had `order_by` or `limit` fields, **preserve them in your corrected plan**
        - These specify sorting and result count (e.g., "top 5 customers", "last 10 logins")
        - Only remove them if they're directly causing the error

        ---

        ## Instructions

        Analyze the error and provide a **corrected plan** (not a query - the query will be regenerated).

        Provide:
        - Reasoning explaining what caused the error and how the plan was corrected
        - A complete corrected plan with the corrections applied
         """  # noqa: E501
    )

    # Get structured LLM (handles method="json_schema" for Ollama automatically)
    structured_llm = get_structured_llm(
        ErrorCorrection, model_name=os.getenv("AI_MODEL"), temperature=0.3
    )

    # Retry loop for handling output parsing errors
    response = None
    last_parsing_error = None
    validation_feedback = None

    for correction_retry in range(MAX_ERROR_CORRECTION_RETRIES):
        try:
            # Add validation feedback if this is a retry
            current_prompt = prompt
            if validation_feedback and correction_retry > 0:
                current_prompt = f"""{prompt}

IMPORTANT VALIDATION ERROR FROM PREVIOUS ATTEMPT:
{validation_feedback}

Please ensure your corrected_plan field:
1. Includes ALL tables referenced in join_edges in the selections array
2. Uses correct column names from the schema
3. Follows all validation rules

Generate a corrected response now.
"""

            logger.info(
                "Invoking LLM for error correction",
                extra={"correction_retry": correction_retry + 1, "has_feedback": validation_feedback is not None}
            )

            with log_execution_time(logger, "llm_plan_correction_invocation"):
                response = structured_llm.invoke(current_prompt)

            # Success - break out of retry loop
            if response is not None:
                if correction_retry > 0:
                    logger.info(
                        "Successfully parsed error correction after retry",
                        extra={"correction_retry": correction_retry + 1}
                    )
                break

        except OutputParserException as e:
            last_parsing_error = e
            error_msg = str(e)

            # Extract validation error details
            validation_summary = extract_validation_error_details(error_msg)

            logger.warning(
                "Error correction parsing failed",
                extra={
                    "correction_retry": correction_retry + 1,
                    "max_retries": MAX_ERROR_CORRECTION_RETRIES,
                    "validation_error": validation_summary,
                    "retry_count": retry_count,
                },
            )

            # Save failed output to debug file
            from utils.debug_utils import save_debug_file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_debug_file(
                f"failed_error_correction_attempt_{correction_retry + 1}_{timestamp}.json",
                {
                    "attempt": correction_retry + 1,
                    "error_message": error_msg,
                    "validation_summary": validation_summary,
                    "original_error": error_message,
                    "retry_count": retry_count,
                },
                step_name="error_correction_errors",
                include_timestamp=False  # Already in filename
            )

            # Create validation feedback for next retry
            validation_feedback = f"""
{validation_summary}

CRITICAL: Every table in join_edges MUST also appear in selections.
If you need to reference a table in a join, you MUST add it to the selections array first.
"""

            # If this was the last retry, we'll handle it after the loop
            if correction_retry == MAX_ERROR_CORRECTION_RETRIES - 1:
                logger.error(
                    "Failed to parse error correction after all retries",
                    exc_info=True,
                    extra={
                        "total_attempts": MAX_ERROR_CORRECTION_RETRIES,
                        "retry_count": retry_count,
                        "last_error": error_msg,
                    }
                )

        except Exception as e:
            # Handle other unexpected errors
            logger.error(
                "Unexpected error during error correction",
                exc_info=True,
                extra={"retry_count": retry_count, "error": str(e)},
            )
            # Add placeholder entries to arrays so UI can display the error
            return {
                **state,
                "messages": [AIMessage(content=f"Unexpected error during correction: {str(e)}")],
                "last_step": "handle_error",
                "retry_count": state["retry_count"] + 1,
                "corrected_queries": state["corrected_queries"] + [original_query],
                "corrected_plans": state["corrected_plans"] + [original_plan_dict],
                "error_reasoning": state.get("error_reasoning", []) + [f"⚠️ UNEXPECTED ERROR: {str(e)}"],
                "error_history": state.get("error_history", [])
                + [f"Correction unexpected error: {str(e)}"],
            }

    # Check if we failed after all retries
    if response is None:
        error_msg = "Failed to correct query plan after multiple validation attempts."
        if last_parsing_error:
            validation_summary = extract_validation_error_details(str(last_parsing_error))
            error_msg += f" Last error: {validation_summary}"

        logger.error(error_msg, extra={"retry_count": retry_count})

        # Add placeholder entries to arrays so UI can display the parse error
        # This keeps arrays in sync with retry_count
        return {
            **state,
            "messages": [AIMessage(content=error_msg)],
            "last_step": "handle_error",
            "retry_count": state["retry_count"] + 1,
            "corrected_queries": state["corrected_queries"] + [original_query],
            "corrected_plans": state["corrected_plans"] + [original_plan_dict],
            "error_reasoning": state.get("error_reasoning", []) + [f"⚠️ PARSING FAILED: {validation_summary}"],
            "error_history": state.get("error_history", [])
            + [f"Correction parsing failed: {validation_summary}"],
        }

    # Convert the corrected plan to dict for state storage
    corrected_plan_dict = response.corrected_plan.model_dump()

    logger.info(
        "Plan correction completed",
        extra={
            "corrected_plan_intent": response.corrected_plan.intent_summary,
            "reasoning": response.reasoning,
            "corrected_plan": corrected_plan_dict,
        },
    )

    # Check if error correction gave up (shouldn't happen with new prompt guidance)
    corrected_decision = corrected_plan_dict.get("decision", "proceed")
    if corrected_decision == "terminate":
        logger.error(
            "Error correction returned 'terminate' decision - this indicates the LLM "
            "couldn't fix the error. Routing to refinement instead.",
            extra={
                "termination_reason": corrected_plan_dict.get("termination_reason"),
                "reasoning": response.reasoning,
            }
        )
        # Return error state - this will route to refinement if retry_count exhausted
        return {
            **state,
            "messages": [AIMessage(content=f"Error correction failed: {response.reasoning}")],
            "retry_count": state["retry_count"] + 1,
            "error_history": state.get("error_history", [])
            + ["Error correction returned terminate decision"],
            "last_step": "handle_error",
        }

    # Debug: Append this correction to the array (allows tracking multiple attempts)
    from utils.debug_utils import append_to_debug_array
    append_to_debug_array(
        "error_corrections.json",
        {
            "attempt": state["retry_count"] + 1,
            "original_query": original_query,
            "original_plan": original_plan_dict,
            "error": error_message,
            "correction_reasoning": response.reasoning,
            "corrected_plan": corrected_plan_dict,
        },
        step_name="handle_tool_error",
        array_key="corrections"
    )

    # Debug: Track SQL queries during error correction
    append_to_debug_array(
        "generated_sql_queries.json",
        {
            "step": "error_correction",
            "attempt": state["retry_count"] + 1,
            "sql": original_query,
            "error": error_message,
            "status": "failed"
        },
        step_name="handle_tool_error",
        array_key="queries"
    )

    # Note: Error correction goes straight to generate_query, no clarification check
    return {
        **state,
        "messages": [AIMessage(content="Generated corrected query plan")],
        "planner_output": corrected_plan_dict,  # Update the current plan
        "retry_count": state["retry_count"] + 1,
        "corrected_queries": state["corrected_queries"] + [original_query],
        "corrected_plans": state["corrected_plans"] + [original_plan_dict],
        "error_reasoning": state.get("error_reasoning", []) + [response.reasoning],
        "last_step": "handle_tool_error",
    }
