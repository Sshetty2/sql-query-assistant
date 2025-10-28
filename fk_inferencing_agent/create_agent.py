"""Create the FK Inferencing Agent workflow."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.nodes.initialize import initialize_node
from fk_inferencing_agent.nodes.load_next_row import load_next_row_node
from fk_inferencing_agent.nodes.find_candidates import find_candidates_node
from fk_inferencing_agent.nodes.evaluate_ambiguity import evaluate_ambiguity_node
from fk_inferencing_agent.nodes.auto_select import auto_select_node
from fk_inferencing_agent.nodes.request_decision import request_decision_node
from fk_inferencing_agent.nodes.record_decision import record_decision_node
from fk_inferencing_agent.nodes.finalize import finalize_node


def route_from_start(state: FKInferencingState) -> Literal["initialize"]:
    """
    Always initialize to ensure schema and vector store are available.
    The initialize node will check if Excel exists and skip creation if so.

    Args:
        state: Current workflow state

    Returns:
        "initialize" always
    """
    if os.path.exists(state["excel_path"]):
        print(f"[PASS] Found existing Excel: {state['excel_path']}")
        print("[INFO] Resuming from last checkpoint...\n")
    else:
        print("[INFO] No existing Excel found - initializing...\n")
    return "initialize"


def route_after_evaluate(
    state: FKInferencingState,
) -> Literal["auto_select", "request_decision", "record_decision"]:
    """
    Route based on score gap threshold or existing decision.

    Args:
        state: Current workflow state

    Returns:
        "record_decision" if decision already made (e.g., skipped),
        "auto_select" if gap >= threshold,
        "request_decision" otherwise
    """
    # If a decision was already made (e.g., no candidates, error), record it directly
    if state.get("decision_type"):
        return "record_decision"

    if state["score_gap"] >= state["threshold"]:
        return "auto_select"
    else:
        return "request_decision"


def route_after_record(
    state: FKInferencingState,
) -> Literal["load_next_row", "finalize"]:
    """
    Continue processing or finalize.

    Args:
        state: Current workflow state

    Returns:
        "load_next_row" if more rows, "finalize" if done or user quit
    """
    if state.get("user_quit"):
        return "finalize"
    elif state.get("has_next_row"):
        return "load_next_row"
    else:
        return "finalize"


def create_fk_inferencing_agent():
    """
    Create the FK inferencing agent workflow.

    Returns:
        Compiled LangGraph workflow with checkpointer
    """
    workflow = StateGraph(FKInferencingState)

    # Add nodes
    workflow.add_node("initialize", initialize_node)
    workflow.add_node("load_next_row", load_next_row_node)
    workflow.add_node("find_candidates", find_candidates_node)
    workflow.add_node("evaluate_ambiguity", evaluate_ambiguity_node)
    workflow.add_node("auto_select", auto_select_node)
    workflow.add_node("request_decision", request_decision_node)
    workflow.add_node("record_decision", record_decision_node)
    workflow.add_node("finalize", finalize_node)

    # Conditional routing from START
    workflow.add_conditional_edges(START, route_from_start)

    # Linear flow after initialization
    workflow.add_edge("initialize", "load_next_row")
    workflow.add_edge("load_next_row", "find_candidates")
    workflow.add_edge("find_candidates", "evaluate_ambiguity")

    # Branch based on ambiguity
    workflow.add_conditional_edges("evaluate_ambiguity", route_after_evaluate)

    # Both paths converge to record_decision
    workflow.add_edge("auto_select", "record_decision")
    workflow.add_edge("request_decision", "record_decision")

    # Loop or finalize
    workflow.add_conditional_edges("record_decision", route_after_record)

    # End
    workflow.add_edge("finalize", END)

    # Compile with checkpointer (needed for interrupt)
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
