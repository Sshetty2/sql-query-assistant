"""Refine the SQL query based on the results."""

import os
import json
from typing import Dict, Any
from textwrap import dedent
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from agent.state import State
from langchain_core.messages import AIMessage
from models.planner_output import PlannerOutput
from utils.llm_factory import get_structured_llm
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


class QueryRefinement(BaseModel):
    """Pydantic model for refining a query plan."""

    reasoning: str = Field(
        description="Explanation of how and why the plan was refined"
    )
    refined_plan: PlannerOutput = Field(
        description="The refined query plan that should return results"
    )


def refine_query(state: State) -> Dict[str, Any]:
    """
    Refine the query plan because the query returned no results.
    Broaden the plan to try to get results.
    """
    original_query = state["query"]
    original_plan = state["planner_output"]
    user_question = state["user_question"]
    refined_count = state.get("refined_count", 0)

    logger.info(
        "Starting plan refinement for no results",
        extra={"refined_count": refined_count, "original_query": original_query[:200]},
    )

    # Use filtered schema if available, otherwise use full schema
    schema_info = state.get("filtered_schema") or state["schema"]

    refined_plans = state.get("refined_plans", [])

    # Format previous attempts for display
    if refined_plans:
        previous_attempts_formatted = "\n".join(
            [
                f"{i}. Intent: {plan.get('intent_summary', 'N/A')}"
                for i, plan in enumerate(refined_plans, 1)
            ]
        )
    else:
        previous_attempts_formatted = "No previous refinement attempts"

    # Format the original plan for display
    # Ensure plan is a dict (in case it's a Pydantic model)
    if hasattr(original_plan, "model_dump"):
        original_plan_dict = original_plan.model_dump()
    else:
        original_plan_dict = original_plan

    original_plan_json = json.dumps(original_plan_dict, indent=2)

    # Create the prompt
    prompt = dedent(
        f"""
        # Query Plan Refinement

        ## We are trying to refine a query plan that generated a query returning no results.

        The query was generated deterministically from this plan, but returned zero rows.
        Your task is to refine the **plan** so that when regenerated, the query will return results.

        ## Original User Question

        {user_question}

        ## Original Query Plan

        ```json
        {original_plan_json}
        ```

        ## Generated Query (from above plan)

        ```sql
        {original_query}
        ```

        **Result:** No rows returned

        ## Previous Refinement Attempts

        {previous_attempts_formatted}

        ## Database Schema

        ```json
        {schema_info}
        ```

        ---

        ## Refinement Strategy

        The query returned no results. Consider these approaches to broaden the plan:

        - **Verify column and table names** - Double-check the schema to ensure correct names are used
        - **Broaden filter predicates** - Relax strict filter conditions that may be too restrictive
        - **Use LIKE patterns in filters** - Replace exact value matches with pattern matching where appropriate
        - **Check for NULL handling** - Ensure filters account for NULL values if needed
        - **Add OR conditions in filters** - Use OR logic where multiple criteria could apply
        - **Remove restrictive time filters** - If present, time filters might be too restrictive
        - **Simplify joins** - Complex joins might be filtering out all results
        - **Check join_edges** - Ensure join columns are correct and exist in both tables

        ---

        ## Instructions

        Analyze why the query returned no results and provide a **refined plan** (not a query - the query will be regenerated).

        **CRITICAL: Decision Field Requirements**

        > **"With great power comes great responsibility."**

        **YOU MUST USE `decision="proceed"` OR `decision="clarify"` IN YOUR REFINED PLAN!**

        - **NEVER EVER use `decision="terminate"`** - This will cause the entire workflow to fail
        - If you identified tables and columns to query → you MUST use `decision="proceed"`
        - If you created a refined plan structure → you MUST use `decision="proceed"`
        - If you're uncertain but have a plan → use `decision="clarify"` with ambiguities
        - Refinement is about **broadening the plan**, not giving up on the query
        - Using `decision="terminate"` will trigger a validation error and waste the refinement attempt

        **Rule of thumb:** If you wrote ANY refined `selections`, `join_edges`, or `filters`, you MUST use `decision="proceed"` or `decision="clarify"`.

        ---

        Provide:
        - Reasoning explaining why no results were returned and how the plan was refined
        - A complete refined plan with the refinements applied
        """  # noqa: E501
    )

    # Get structured LLM (handles method="json_schema" for Ollama automatically)
    structured_llm = get_structured_llm(
        QueryRefinement, model_name=os.getenv("AI_MODEL_REFINE"), temperature=0.6
    )

    try:
        with log_execution_time(logger, "llm_refine_plan_invocation"):
            response = structured_llm.invoke(prompt)

        # Convert the refined plan to dict for state storage
        refined_plan_dict = response.refined_plan.model_dump()
    except Exception as e:
        logger.error(
            "Failed to parse refinement response from LLM",
            exc_info=True,
            extra={
                "refined_count": refined_count,
                "error": str(e)
            }
        )
        # Return state with error message - this will trigger cleanup on next iteration
        # since refined_count will exceed max attempts
        return {
            **state,
            "messages": [AIMessage(content=f"Error refining query plan: {str(e)}")],
            "last_step": "refine_query",
            "refined_count": state["refined_count"] + 1,
            "error_history": state.get("error_history", []) + [f"Refinement parsing error: {str(e)}"],
        }

    logger.info(
        "Plan refinement completed",
        extra={
            "refined_plan_intent": response.refined_plan.intent_summary,
            "refined_plan": refined_plan_dict,
            "reasoning": response.reasoning,
        },
    )

    # Debug: Append this refinement to the array (allows tracking multiple attempts)
    from utils.debug_utils import append_to_debug_array
    append_to_debug_array(
        "query_refinements.json",
        {
            "attempt": state["refined_count"] + 1,
            "original_query": original_query,
            "original_plan": original_plan_dict,
            "refinement_reasoning": response.reasoning,
            "refined_plan": refined_plan_dict,
        },
        step_name="refine_query",
        array_key="refinements"
    )

    # Debug: Track SQL queries during refinement
    append_to_debug_array(
        "generated_sql_queries.json",
        {
            "step": "refinement",
            "attempt": state["refined_count"] + 1,
            "sql": original_query,
            "reason": "no results returned",
            "status": "no_results"
        },
        step_name="refine_query",
        array_key="queries"
    )

    # Note: Query refinement goes straight to generate_query, no clarification check
    return {
        **state,
        "messages": [AIMessage(content="Query plan refined for broader results")],
        "planner_output": refined_plan_dict,  # Update the current plan
        "last_step": "refine_query",
        "refined_queries": state["refined_queries"] + [original_query],
        "refined_plans": state["refined_plans"] + [original_plan_dict],
        "refined_reasoning": state["refined_reasoning"] + [response.reasoning],
        "refined_count": state["refined_count"] + 1,
    }
