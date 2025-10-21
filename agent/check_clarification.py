"""Check if planner needs clarification and generate query suggestions."""

import os
from textwrap import dedent
from typing import Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from agent.state import State
from utils.llm_factory import get_structured_llm
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


class ClarificationSuggestions(BaseModel):
    """Pydantic model for clarification suggestions."""

    suggestions: list[str] = Field(
        description="List of 3-5 suggested query rewrites to help clarify the user's intent",
        min_length=3,
        max_length=5,
    )


def check_clarification(state: State) -> Dict[str, Any]:
    """
    Check if the planner requested clarification and generate helpful query suggestions.

    If clarification is needed, uses an LLM to analyze the ambiguities and generate
    suggested query rewrites that the user can select from.
    """
    planner_output = state["planner_output"]

    if not planner_output:
        # No planner output, continue normally
        return {
            **state,
            "last_step": "check_clarification",
        }

    decision = planner_output["decision"]

    # Check if clarification is needed
    if decision != "clarify":
        # No clarification needed, continue normally
        return {
            **state,
            "needs_clarification": False,
            "last_step": "check_clarification",
        }

    # Clarification is needed - generate suggestions
    logger.info(
        "Planner requested clarification, generating query suggestions",
        extra={"decision": decision},
    )

    user_question = state["user_question"]
    ambiguities = planner_output["ambiguities"]
    intent_summary = planner_output["intent_summary"]

    # Format ambiguities for the prompt
    if ambiguities:
        ambiguities_formatted = "\n".join([f"- {amb}" for amb in ambiguities])
    else:
        ambiguities_formatted = "No specific ambiguities provided"

    # Create prompt for generating suggestions
    prompt = dedent(
        f"""
        # Query Clarification Assistance

        ## Original User Question

        {user_question}

        ## Planner Analysis

        **Intent Summary:** {intent_summary if intent_summary else 'N/A'}

        **Ambiguities Identified:**
        {ambiguities_formatted}

        ---

        ## Task

        The planner identified ambiguities in the user's question that prevent generating a precise query.

        Generate 3-5 suggested query rewrites that:
        - Address the specific ambiguities mentioned
        - Are clear, specific, and unambiguous
        - Maintain the user's original intent where possible
        - Provide different interpretations of what the user might mean
        - Are phrased as natural questions the user could ask

        ## Examples of Good Suggestions

        **Original:** "Show me users"
        **Suggestions:**
        - "Show me all active users"
        - "Show me users created in the last 30 days"
        - "Show me users with admin role"

        **Original:** "Get computer data"
        **Suggestions:**
        - "Get all computers with their operating system details"
        - "Get computers scanned in the last 7 days"
        - "Get computers with installed applications"

        ---

        ## Instructions

        Return a JSON object with:
        - `suggestions`: A list of 3-5 suggested query rewrites
        """  # noqa: E501
    )

    # Get structured LLM
    structured_llm = get_structured_llm(
        ClarificationSuggestions,
        model_name=os.getenv("AI_MODEL"),
        temperature=0.7,
    )

    with log_execution_time(logger, "llm_clarification_suggestions"):
        response = structured_llm.invoke(prompt)

    suggestions = response.suggestions

    logger.info(
        "Generated clarification suggestions",
        extra={"suggestion_count": len(suggestions)},
    )

    return {
        **state,
        "messages": [AIMessage(content="Clarification needed - generated suggestions")],
        "needs_clarification": True,
        "clarification_suggestions": suggestions,
        "last_step": "check_clarification",
    }
