"""Conversational router for determining how to handle follow-up queries."""

import os
import json
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from models.router_output import RouterOutput
from utils.llm_factory import get_structured_llm, invoke_with_timeout
from utils.logger import get_logger, log_execution_time
from agent.state import State

load_dotenv()
logger = get_logger()


def create_router_prompt(**format_params):
    """Create a simple formatted prompt for the conversational router.

    Args:
        format_params: Parameters to format into the prompt

    Returns:
        Formatted prompt string with system instructions and user input
    """

    system_instructions = """SYSTEM INSTRUCTIONS:

Analyze follow-up user requests in context of previous queries and decide how to handle them.

Decision Types - Choose one of three routing decisions:

1. **revise_query_inline**: Use when the user wants a SMALL change to the SQL query itself:
   - Adding or removing a single column
   - Changing LIMIT/TOP value
   - Minor syntax adjustments
   - Simple query modifications that don't require replanning

   For this decision, generate the complete revised SQL query in `revised_query`.

2. **update_plan**: Use when the user wants MINOR modifications to the query plan:
   - Adding/removing/modifying filters
   - Changing sort order or grouping
   - Adjusting existing joins
   - Changes that affect the plan but use the same core tables

   For this decision, provide clear instructions in `routing_instructions` describing
   what the planner should modify.

3. **rewrite_plan**: Use when the user wants MAJOR changes requiring a new plan:
   - Querying different tables or entities
   - Completely different business question
   - Adding tables that require new join logic
   - Fundamental shift in query intent

   For this decision, provide high-level guidance in `routing_instructions` about
   the new direction.

Guidelines:

- **Be conservative with revise_query_inline**: Only use for trivial SQL modifications.
  If unsure whether the change affects the plan, choose update_plan instead.

- **Context is key**: Consider the entire conversation history, not just the latest request.
  The user might reference earlier queries or results.

- **Be specific in instructions**: When routing to the planner, provide actionable guidance.
  Bad: "Update the query"
  Good: "Add a filter on the Status column to only show records where Status = 'Active'"

- **Preserve intent**: Ensure the decision maintains the user's original intent while
  incorporating their requested changes.

Output Format:

Return ONLY a valid RouterOutput JSON object with:
- decision: Routing choice
- reasoning: Clear explanation of decision
- revised_query: Complete SQL (only if decision = "revise_query_inline")
- routing_instructions: Instructions for planner (only if decision = "update_plan" or "rewrite_plan")
"""

    user_input = """USER INPUT:

Conversation History:
{conversation_history}

Previous SQL Queries:
{query_history}

Previous Query Plans:
{plan_history}

Current Database Schema (filtered):
{schema}

Latest User Request:
{latest_request}"""

    # Format and combine
    formatted_system = system_instructions
    formatted_user = user_input.format(**format_params)

    return f"{formatted_system}\n\n{formatted_user}"


def format_conversation_history(user_questions: list[str]) -> str:
    """Format the conversation history for the prompt."""
    if not user_questions:
        return "No previous questions"

    history = []
    for i, question in enumerate(user_questions[:-1], 1):  # Exclude latest
        history.append(f"{i}. {question}")

    return "\n".join(history) if history else "No previous questions"


def format_query_history(queries: list[str]) -> str:
    """Format the SQL query history for the prompt."""
    if not queries:
        return "No previous queries"

    history = []
    for i, query in enumerate(queries, 1):
        # Truncate long queries for readability
        query_preview = query if len(query) <= 200 else query[:197] + "..."
        history.append(f"Query {i}:\n{query_preview}\n")

    return "\n".join(history)


def format_plan_history(planner_outputs: list[dict]) -> str:
    """Format the planner output history for the prompt."""
    if not planner_outputs:
        return "No previous plans"

    history = []
    for i, plan in enumerate(planner_outputs, 1):
        # Extract key information from plan
        intent = plan.get("intent_summary", "N/A")
        tables = [sel.get("table") for sel in plan.get("selections", [])]
        history.append(
            f"Plan {i}:\n  Intent: {intent}\n  Tables: {', '.join(tables)}\n"
        )

    return "\n".join(history)


def conversational_router(state: State):
    """
    Route follow-up queries based on conversation context.

    Analyzes the user's latest request in context of previous queries and plans,
    then decides whether to:
    1. Revise the SQL query inline (for small changes)
    2. Update the existing plan (for minor modifications)
    3. Rewrite the plan completely (for major changes)
    """
    latest_request = state["user_question"]
    logger.info(
        "Starting conversational routing", extra={"latest_request": latest_request}
    )

    try:
        user_questions = state.get("user_questions", [])
        queries = state.get("queries", [])
        planner_outputs = state.get("planner_outputs", [])
        schema = state.get("schema", [])

        # Format context for the prompt
        conversation_history = format_conversation_history(user_questions)
        query_history = format_query_history(queries)
        plan_history = format_plan_history(planner_outputs)

        # Create the prompt
        prompt = create_router_prompt(
            conversation_history=conversation_history,
            query_history=query_history,
            plan_history=plan_history,
            schema=json.dumps(schema, indent=2),
            latest_request=latest_request,
        )

        # Get structured LLM
        # (handles method="json_schema" for Ollama automatically)
        structured_llm = get_structured_llm(
            RouterOutput, model_name=os.getenv("AI_MODEL"), temperature=0.3
        )

        with log_execution_time(logger, "llm_router_invocation"):
            # Use invoke_with_timeout for proper timeout handling (especially for Ollama)
            # 75s timeout, 2 retries = up to 150s total before failing
            router_output = invoke_with_timeout(structured_llm, prompt)

        if router_output is None:
            logger.warning("Router failed to make a decision")
            return {
                **state,
                "messages": [
                    AIMessage(content="Error: Router failed to make a decision")
                ],
                "last_step": "conversational_router",
            }

        # Update state based on decision
        decision = router_output.decision

        logger.info(
            "Conversational routing completed",
            extra={"decision": decision, "reasoning": router_output.reasoning},
        )

        if decision == "revise_query_inline":
            # Validate that revised_query was actually provided
            if (
                router_output.revised_query is None
                or not router_output.revised_query.strip()
            ):
                logger.warning(
                    "Router chose 'revise_query_inline' but did not provide a revised_query. "
                    "Falling back to 'rewrite_plan' routing."
                )
                # Fall back to rewrite_plan to avoid null query execution
                return {
                    **state,
                    "messages": [
                        AIMessage(
                            content=f"Router fallback: Rewriting plan due to missing query - {router_output.reasoning}"
                        )
                    ],
                    "router_mode": "rewrite",
                    "router_instructions": (
                        "Router attempted inline revision but failed to generate query. "
                        "Please generate a new plan and query based on the user's request."
                    ),
                    "last_step": "conversational_router",
                }

            # Set the revised query directly
            return {
                **state,
                "messages": [
                    AIMessage(
                        content=f"Router decision: Inline query revision - {router_output.reasoning}"
                    )
                ],
                "query": router_output.revised_query,
                "router_mode": None,  # No need for planner
                "router_instructions": None,
                "last_step": "conversational_router",
            }

        elif decision == "update_plan":
            # Route to planner with update instructions
            return {
                **state,
                "messages": [
                    AIMessage(
                        content=f"Router decision: Update plan - {router_output.reasoning}"
                    )
                ],
                "router_mode": "update",
                "router_instructions": router_output.routing_instructions,
                "last_step": "conversational_router",
            }

        elif decision == "rewrite_plan":
            # Route to planner with rewrite instructions
            return {
                **state,
                "messages": [
                    AIMessage(
                        content=f"Router decision: Rewrite plan - {router_output.reasoning}"
                    )
                ],
                "router_mode": "rewrite",
                "router_instructions": router_output.routing_instructions,
                "last_step": "conversational_router",
            }

        else:
            return {
                **state,
                "messages": [AIMessage(content=f"Unknown router decision: {decision}")],
                "last_step": "conversational_router",
            }

    except TimeoutError as e:
        logger.error(f"Router LLM timeout: {str(e)}", exc_info=True)
        # Return state that routes to planner with fallback instructions
        return {
            **state,
            "messages": [
                AIMessage(
                    content=f"Router timeout - falling back to full planning: {str(e)}"
                )
            ],
            "router_mode": "rewrite",
            "router_instructions": (
                "Router timed out while analyzing the conversation. "
                "Please generate a new plan and query based on the user's request."
            ),
            "last_step": "conversational_router",
        }

    except Exception as e:
        logger.error(f"Error in conversational router: {str(e)}", exc_info=True)
        return {
            **state,
            "messages": [
                AIMessage(content=f"Error in conversational router: {str(e)}")
            ],
            "last_step": "conversational_router",
        }
