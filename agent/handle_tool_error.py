"""Handle errors from query execution by having LLM analyze and suggest fixes."""

import os
import json
from dotenv import load_dotenv
from textwrap import dedent
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from models.planner_output import PlannerOutput
from utils.llm_factory import get_structured_llm
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


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
        # Query Plan Error Correction

        ## We are trying to correct a query plan that generated a failing SQL query.

        The query was generated deterministically from this plan, but the execution raised an error.
        Your task is to correct the **plan** so that when regenerated, the query will succeed.

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
        - Keep the user's original question and intent in mind
        - Don't remove essential columns or tables unless they're causing errors

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

    try:
        with log_execution_time(logger, "llm_plan_correction_invocation"):
            response = structured_llm.invoke(prompt)

        # Convert the corrected plan to dict for state storage
        corrected_plan_dict = response.corrected_plan.model_dump()
    except Exception as e:
        logger.error(
            "Failed to parse error correction response from LLM",
            exc_info=True,
            extra={"retry_count": retry_count, "error": str(e)},
        )
        # Return state with error message - this will trigger cleanup on next iteration
        # since retry_count will exceed max attempts
        return {
            **state,
            "messages": [AIMessage(content=f"Error correcting query plan: {str(e)}")],
            "last_step": "handle_error",
            "retry_count": state["retry_count"] + 1,
            "error_history": state.get("error_history", [])
            + [f"Correction parsing error: {str(e)}"],
        }

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

    # Debug: Save the corrected planner output to a file
    debug_output_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "debug/debug_corrected_planner_output.json",
    )
    try:
        with open(debug_output_path, "w", encoding="utf-8") as f:
            json.dump(corrected_plan_dict, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save debug planner output: {e}")

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
