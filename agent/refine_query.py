"""Refine the SQL query based on the results."""

import os
from typing import Dict, Any
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
        extra={
            "refined_count": refined_count,
            "original_query": original_query[:200]
        }
    )

    # Use filtered schema if available, otherwise use full schema
    schema_info = state.get("filtered_schema") or state["schema"]

    refined_queries = state["refined_queries"]

    previous_attempts = ""
    if refined_queries:
        previous_attempts = (
            "Previous refinement attempts that still returned no results:\n"
        )
        for i, query in enumerate(refined_queries, 1):
            previous_attempts += f"{i}. {query}\n"

    # Create the prompt
    prompt = f"""SYSTEM INSTRUCTIONS:

Refine SQL queries that returned no results by broadening them intelligently.

USER INPUT:

Original question: {user_question}

Original query: {original_query}

Truncated Database schema: {schema_info}

{previous_attempts}

Task: Change the content of the query so that it makes logical sense. Consider:
1. Using the correct column or table names; Double check the schema to make sure we are using the correct names.
2. Broadening WHERE clauses
3. Using LIKE instead of exact matches
4. Checking for NULL values
5. Using OR conditions where appropriate

Return a JSON object with:
- reasoning: Explanation of how and why the query was refined
- sql_query: The refined SQL query"""

    # Get structured LLM (handles method="json_schema" for Ollama automatically)
    structured_llm = get_structured_llm(
        QueryRefinement, model_name=os.getenv("AI_MODEL_REFINE"), temperature=0.7
    )

    with log_execution_time(logger, "llm_refine_query_invocation"):
        response = structured_llm.invoke(prompt)

    logger.info(
        "Query refinement completed",
        extra={"refined_query_length": len(response.sql_query)}
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
