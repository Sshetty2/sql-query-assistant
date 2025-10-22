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
        description="List of 3-5 declarative clarification statements that can augment the original query",
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
    if decision == "terminate":
        # Query is being terminated - no clarification suggestions needed
        logger.info(
            "Planner terminated query, skipping clarification suggestions",
            extra={"decision": decision, "termination_reason": planner_output.get("termination_reason")}
        )
        return {
            **state,
            "needs_clarification": False,
            "last_step": "check_clarification",
        }

    if decision != "clarify":
        # No clarification needed, continue normally
        return {
            **state,
            "needs_clarification": False,
            "last_step": "check_clarification",
        }

    # Clarification is needed - generate suggestions
    logger.info(
        "Planner flagged clarification, generating declarative clarification statements",
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

        The planner identified potential ambiguities in the user's question.

        Generate 3-5 declarative clarification statements that:
        - Address the specific ambiguities mentioned
        - Are phrased as DECLARATIVE STATEMENTS (not questions)
        - Can be combined or selected by the user to augment/clarify their original query
        - Provide different interpretations or specifications of what the user might mean
        - Will be sent back to refine the plan, not create a new query

        ## Examples of Good Suggestions

        **Original:** "Show me users"
        **Clarification Statements:**
        - "Only include active users"
        - "Users created in the last 30 days"
        - "Filter to users with admin role"
        - "Include all user statuses"

        **Original:** "Get computer data"
        **Clarification Statements:**
        - "Include operating system details"
        - "Only computers scanned in the last 7 days"
        - "Show installed applications for each computer"
        - "Include hardware specifications"

        **Original:** "Show vulnerabilities"
        **Clarification Statements:**
        - "Only critical and high severity vulnerabilities"
        - "Vulnerabilities discovered in the last 30 days"
        - "Group by affected application"
        - "Include remediation status"

        ---

        ## Instructions

        Generate 3-5 declarative clarification statements (NOT questions).

        Remember: These are clarifications that augment the original query, not new query suggestions.
        They should be combinable and will be used to refine the existing plan.
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
        "Generated clarification statements",
        extra={"suggestion_count": len(suggestions)},
    )

    return {
        **state,
        "messages": [AIMessage(content="Clarification flagged - generated statements for user review")],
        "needs_clarification": True,
        "clarification_suggestions": suggestions,
        "last_step": "check_clarification",
    }
