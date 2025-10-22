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

        ## Previous Error History

        {chr(10).join(['- ' + err for err in error_history]) if error_history else 'No previous errors'}

        ## Database Schema (with column types)

        ```json
        {schema}
        ```

        ---

        ## IMPORTANT: Plan Correction Strategy

        **First Priority - MAINTAIN THE ORIGINAL INTENT:**
        - Keep the user's original question and intent in mind
        - Don't remove essential columns or tables unless they're causing errors

        **Second Priority - Fix Data Type Mismatches:**
        - **Check JOIN columns** - ensure joined columns have compatible data types
        - Review foreign key relationships in the schema to identify correct join columns
        - For example, if joining `tb_Users` to `tb_UserLoginInfo`, check:
          - `tb_UserLoginInfo.UserID` (bigint) should join to `tb_Users.ID` (bigint)
          - NOT `tb_Users.UserID` (nvarchar) - this would cause type conversion errors

        **Third Priority - Verify Schema Accuracy:**
        - Ensure all columns exist in their respective tables
        - Verify column names match exactly (check data types in schema)
        - Remove any malformed table/column references
        - Check that selected columns are valid

        **Fourth Priority - Simplify if Needed:**
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

        Return a JSON object with:
        - `reasoning`: Explanation of what caused the error and how the plan was corrected
        - `corrected_plan`: A complete PlannerOutput object with the corrections applied
         """  # noqa: E501
    )

    # Get structured LLM (handles method="json_schema" for Ollama automatically)
    structured_llm = get_structured_llm(
        ErrorCorrection, model_name=os.getenv("AI_MODEL"), temperature=0.3
    )

    with log_execution_time(logger, "llm_plan_correction_invocation"):
        response = structured_llm.invoke(prompt)

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

    # Debug: Save the corrected planner output to a file
    debug_output_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "debug_corrected_planner_output.json",
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
