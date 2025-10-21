"""Refine the SQL query based on the results."""

import os
from typing import Dict, Any
from textwrap import dedent
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from agent.state import State
from langchain_core.messages import AIMessage
from utils.llm_factory import get_structured_llm
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


class QueryRefinement(BaseModel):
    """Pydantic model for refining a query."""

    reasoning: str = Field(
        description="Explanation of how and why the query was refined"
    )
    sql_query: str = Field(description="The refined SQL query")


def refine_query(state: State) -> Dict[str, Any]:
    """
    Refine the SQL query because the initial results are None.
    Broaden the query to try to get results.
    """
    original_query = state["query"]
    user_question = state["user_question"]
    refined_count = state.get("refined_count", 0)

    logger.info(
        "Starting query refinement",
        extra={"refined_count": refined_count, "original_query": original_query},
    )

    # Use filtered schema if available, otherwise use full schema
    schema_info = state.get("filtered_schema") or state["schema"]

    refined_queries = state["refined_queries"]

    # Format previous attempts for display
    if refined_queries:
        previous_attempts_formatted = "\n".join(
            [f"{i}. {query}" for i, query in enumerate(refined_queries, 1)]
        )
    else:
        previous_attempts_formatted = "No previous refinement attempts"

    # Create the prompt
    prompt = dedent(
        f"""
        # SQL Query Refinement

        ## We are trying to refine a SQL query that returned no results.

        ## Original User Question

        {user_question}

        ## Current Query (returned no results)

        ```sql
        {original_query}
        ```

        ## Previous Refinement Attempts

        {previous_attempts_formatted}

        ## Database Schema

        ```json
        {schema_info}
        ```

        ---

        ## Refinement Strategy

        The query returned no results. Consider these approaches to broaden the query:

        - **Verify column and table names** - Double-check the schema to ensure correct names are used
        - **Broaden WHERE clauses** - Relax strict conditions that may be too restrictive
        - **Use LIKE patterns** - Replace exact matches with pattern matching where appropriate
        - **Check for NULL values** - Add conditions to handle NULL values if needed
        - **Add OR conditions** - Use OR logic where multiple criteria could apply
        - **Remove time filters** - If present, time filters might be too restrictive
        - **Simplify joins** - Complex joins might be filtering out all results

        ---

        ## Instructions

        Analyze why the query returned no results and provide a refined version that broadens the search while maintaining the original intent.

        Return a JSON object with:
        - `reasoning`: Explanation of how and why the query was refined
        - `sql_query`: The refined SQL query
        """  # noqa: E501
    )

    # Get structured LLM (handles method="json_schema" for Ollama automatically)
    structured_llm = get_structured_llm(
        QueryRefinement, model_name=os.getenv("AI_MODEL_REFINE"), temperature=0.6
    )

    with log_execution_time(logger, "llm_refine_query_invocation"):
        response = structured_llm.invoke(prompt)

    logger.info(
        "Query refinement completed",
        extra={"refined_query_length": len(response.sql_query)},
    )

    return {
        **state,
        "messages": [AIMessage(content="Query refined for broader results")],
        "query": response.sql_query,
        "last_step": "refine_query",
        "refined_queries": state["refined_queries"] + [original_query],
        "refined_reasoning": state["refined_reasoning"] + [response.reasoning],
        "refined_count": state["refined_count"] + 1,
    }
