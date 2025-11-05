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
from models.history import RefinementHistory
from utils.llm_factory import get_chat_llm, get_model_for_stage
from utils.logger import get_logger, log_execution_time
from utils.stream_utils import emit_node_status
from utils.debug_utils import append_to_debug_array


load_dotenv()
logger = get_logger()


class QueryRefinement(BaseModel):
    """Pydantic model for refining a query plan (legacy - used for feedback generation)."""

    reasoning: str = Field(
        description="Explanation of how and why the plan was refined"
    )
    refined_plan: PlannerOutput = Field(
        description="The refined query plan that should return results"
    )


def generate_refined_strategy(
    original_query: str,
    original_strategy: str,
    user_question: str,
    refined_plans: list[dict],
    schema: list[dict],
    schema_markdown: str = None,
) -> str:
    """
    Generate a refined strategy directly from empty query results.

    Bypasses pre-planner and generates a refined strategy that should return results.
    The refined strategy will be sent directly to planner for JSON conversion.

    Args:
        original_query: The SQL query that returned no results
        original_strategy: The previous strategy text that returned no results
        user_question: The original user question
        refined_plans: List of previous refinement attempts
        schema: The database schema (filtered/truncated) as list of dicts
        schema_markdown: The database schema formatted as markdown (easier to search)

    Returns:
        Refined strategy text (will be sent to planner)
    """
    # Use markdown schema if available (easier to search), otherwise JSON
    if schema_markdown:
        schema_text = schema_markdown
        schema_format = "markdown"
    else:
        schema_text = json.dumps(schema, indent=2)
        schema_format = "json"

    # Format previous attempts
    if refined_plans:
        previous_attempts_formatted = "\n".join(
            [
                f"{i}. Intent: {plan.get('intent_summary', 'N/A')}"
                for i, plan in enumerate(refined_plans, 1)
            ]
        )
    else:
        previous_attempts_formatted = "No previous refinement attempts"

    prompt = dedent(
        f"""
        # Generate Refined Strategy from Empty Results

        ## System Overview

        We're building a SQL query assistant that converts natural language to SQL queries.
        The system uses a **two-stage planning approach**:

        1. **Pre-Planner** (stage 1) - Creates a text-based strategic plan for NEW queries
        2. **Planner** (stage 2) - Converts strategy to structured JSON
        3. **SQL Generator** - Deterministically converts JSON to SQL

        **Your Role:** You're the **query refinement strategist**. A query was executed successfully
        but **returned zero results**. Generate a REFINED STRATEGY that should return results.
        Your output will go DIRECTLY to the planner (skip pre-planner).

        **Important:** Generate a COMPLETE refined strategy in the same format as the original strategy below.
        This is NOT feedback - this IS the refined strategy that will be converted to JSON.

        ---

        ## User's Original Question
        ```
        {user_question}
        ```

        ## Previous Strategy (Returned No Results)
        ```
        {original_strategy}
        ```

        ## Generated SQL Query (from previous strategy)
        ```sql
        {original_query}
        ```

        **Result:** Query executed successfully but returned 0 rows

        ## Database Schema (Reference for Refinements)
        ```{schema_format}
        {schema_text}
        ```

        ## Previous Refinement Attempts
        {previous_attempts_formatted}

        ---

        ## Your Task

        Generate a REFINED STRATEGY that should return results. Use the EXACT format of the original strategy above.

        **Critical Requirements:**

        0. **VERIFY table ownership for EVERY column** (TOP PRIORITY):
           a) Before using ANY column, find it in the schema above
           b) Note which SPECIFIC table contains that column
           c) Use the EXACT table.column reference from schema
           d) Common mistake: Assuming columns are in the "main" table
           e) Reality: Check detail tables (tables with suffixes like "Details", "Map", "Info")

           **Example Process:**
           - Query failed with no results for "items with specific attribute"
           - Step 1: Search schema above for columns related to "attribute"
           - Step 2: Find which table actually contains the relevant column (check ALL tables)
           - Step 3: If found in tb_DetailTable (NOT tb_MainTable!), use tb_DetailTable.AttributeColumn
           - Step 4: If tb_DetailTable is not in the filtered schema above, DO NOT use it. Find an alternative.
           - Step 5: Add necessary join: tb_MainTable.ID = tb_DetailTable.ForeignKeyID

           **CRITICAL:** Only use tables that appear in the schema above!

        1. **Preserve user intent**: Don't change WHAT the user asked for, only adjust HOW to find it

        2. **Broaden the approach**: Common adjustments that help find results:
           - Use LIKE patterns instead of exact matches
           - Broaden date/time filters
           - Remove overly restrictive conditions
           - Simplify complex joins
           - Check for NULL handling
           - Try related tables if current ones have no data

        3. **Verify columns exist**: Before using ANY column:
           a) Find the table in the schema above
           b) Check the table's actual columns
           c) Confirm the column EXISTS in that list

        4. **Verify joins**: Ensure joins use correct foreign key relationships from schema

        5. **ZERO tolerance for hallucinations**: NEVER use a column that doesn't appear in the schema

        6. **Keep same format**: Use the same markdown structure, headings, and sections as the original strategy

        **Common No-Results Fixes:**
        - Too restrictive filters → Broaden filter conditions or use LIKE patterns
        - Wrong column names → Use correct column names from schema
        - Wrong table selection → Try related tables that might have the data
        - NULL value handling → Add IS NOT NULL or COALESCE
        - Too many joins → Simplify join structure
        - Wrong join columns → Use correct FK relationships from schema
        - Time filters too narrow → Broaden time range

        **Output Format:**
        Generate a complete refined strategy in markdown format with these sections:
        - **Tables**: List of tables needed
        - **Columns**: List of columns to select/filter
        - **Joins**: How tables connect (use FK relationships from schema)
        - **Filters**: Conditions to apply (consider broadening these)
        - **Aggregations**: Any grouping/aggregation needed
        - **Ordering**: How to sort results
        - **Limiting**: Result limit

        **IMPORTANT:**
        - Output ONLY the refined strategy text (no preamble, no "here's the strategy")
        - Use the EXACT same format as the original strategy above
        - Verify ALL columns exist in the schema before including them
        - Focus on broadening filters or trying related tables to find results
    """
    ).strip()

    try:
        refinement_model = get_model_for_stage("refinement")
        llm = get_chat_llm(model_name=refinement_model)

        with log_execution_time(logger, "llm_refined_strategy_generation"):
            result = llm.invoke(prompt)

        # Extract text content from LangChain message
        refined_strategy = result.content if hasattr(result, "content") else str(result)

        return refined_strategy.strip()

    except Exception as e:
        logger.error(f"Error generating refined strategy: {str(e)}", exc_info=True)
        # Fallback: Return original strategy with refinement note
        return f"""{original_strategy}

---

**REFINEMENT NOTE:**
Failed to generate refined strategy due to: {str(e)[:100]}
Query returned 0 rows. Consider broadening filters or checking table/column selections."""


def refine_query(state: State) -> Dict[str, Any]:
    """
    Generate refined strategy directly because query returned no results.
    Routes to planner with refined strategy (bypasses pre-planner).
    """
    original_query = state["query"]
    original_plan = state["planner_output"]
    user_question = state["user_question"]
    refinement_iteration = state.get("refinement_iteration", 0)

    # Get max refinement attempts from environment
    max_refinements = int(os.getenv("REFINE_COUNT")) if os.getenv("REFINE_COUNT") else 3

    # Get the strategy that led to no results (could be from pre-planner or previous revision)
    previous_strategy = state.get("revised_strategy") or state.get(
        "pre_plan_strategy", ""
    )

    # Format the original plan for history tracking
    if hasattr(original_plan, "model_dump"):
        original_plan_dict = original_plan.model_dump()
    else:
        original_plan_dict = original_plan

    logger.warning(
        f"Query returned no results (iteration {refinement_iteration + 1}/{max_refinements})",
        extra={
            "refinement_iteration": refinement_iteration,
        },
    )

    # Check if we've exhausted iteration limit
    if refinement_iteration >= max_refinements:
        logger.error(
            f"Refinement iteration limit reached ({max_refinements} iterations), terminating",
            extra={"refinement_iteration": refinement_iteration},
        )
        return {
            **state,
            "messages": [
                AIMessage(
                    content=f"No results after {refinement_iteration} refinement attempts"
                )
            ],
            "planner_output": original_plan_dict,
            "needs_termination": True,
            "termination_reason": f"Query returned no results after {max_refinements} refinement attempts",
            "last_step": "refine_query",
        }

    # Use truncated schema if available (preferred for LLM context), otherwise filtered
    schema = (
        state.get("truncated_schema") or state.get("filtered_schema") or state["schema"]
    )

    # Extract previous refinement plans from history for prompt context
    refinement_history = state.get("refinement_history", [])
    refined_plans = [record.get("plan", {}) for record in refinement_history]

    # Generate refined strategy directly (bypasses pre-planner)
    # Use markdown schema if available (easier for LLM to search)
    schema_markdown = state.get("schema_markdown", None)

    refined_strategy = generate_refined_strategy(
        original_query=original_query,
        original_strategy=previous_strategy,
        user_question=user_question,
        refined_plans=refined_plans,
        schema=schema,
        schema_markdown=schema_markdown,
    )

    logger.info(
        "Generated refined strategy (bypassing pre-planner)",
        extra={
            "strategy_length": len(refined_strategy),
            "refinement_iteration": refinement_iteration + 1,
        },
    )

    # Create structured refinement history object
    refinement_record = RefinementHistory(
        strategy=refined_strategy,
        plan=original_plan_dict,
        query=original_query,
        reasoning="Query returned 0 results. Generated refined strategy to broaden filters and improve result retrieval.",  # noqa: E501
        iteration=refinement_iteration + 1,
    )

    append_to_debug_array(
        "refinement_history.json",
        {
            **refinement_record.model_dump(),
            "previous_strategy": previous_strategy,
        },
        step_name="refine_query",
        array_key="refinements",
    )

    emit_node_status("refine_query", "completed")

    return {
        **state,
        "messages": [
            AIMessage(
                content=f"Query returned no results, routing to planner with refined strategy "
                f"(attempt {refinement_iteration + 1}/{max_refinements})"
            )
        ],
        "planner_output": original_plan_dict,  # Keep current plan for history
        "revised_strategy": refined_strategy,  # Refined strategy for planner
        "refinement_iteration": refinement_iteration + 1,  # Increment counter
        "refinement_history": state.get("refinement_history", [])
        + [refinement_record.model_dump()],
        "last_step": "refine_query",
    }
