"""Request decision node - interrupt workflow for human input."""

import traceback
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger

logger = get_logger("fk_agent")


def request_decision_node(state: FKInferencingState) -> dict:
    """
    Interrupt workflow and request human decision.

    This node uses LangGraph's interrupt() to pause execution
    and wait for user input from the CLI.

    Args:
        state: Current workflow state

    Returns:
        Dict with updated state (chosen_table, chosen_score, decision_type, notes, user_quit)
        Routing is handled by conditional edge based on user_quit flag
    """
    try:
        logger.info(f"[request_decision] Starting node (last_step: {state.get('last_step', 'unknown')})")
        logger.info(f"Requesting user decision for {state['current_table']}.{state['current_column']}")

        # Prepare interrupt data
        interrupt_data = {
            "table": state["current_table"],
            "column": state["current_column"],
            "base_name": state["current_base_name"],
            "candidates": [
                {"index": i+1, "table": t, "score": f"{s:.3f}"}
                for i, (t, s) in enumerate(state["candidates"][:5])
            ],
            "score_gap": state["score_gap"],
            "threshold": state["threshold"]
        }

        print("\n[!] AMBIGUOUS - Please choose:")
        print("  [1-5] Select candidate")
        print("  [s]   Skip this FK")
        print("  [q]   Quit and save")

        # Pause and wait for user input
        # This returns the value passed to Command(resume=...)
        user_choice = interrupt(interrupt_data)

        logger.info(f"Received user choice: {user_choice}")

        # Process user choice
        if user_choice == "q":
            logger.info("User chose to quit")
            print("[WARN] User quit session")
            return {
                **state,
                "user_quit": True,
                "chosen_table": None,
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "User quit session",
                "last_step": "request_decision_quit"
            }
        elif user_choice == "s":
            logger.info("User chose to skip")
            print("[WARN] User skipped this FK")
            return {
                **state,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "User skipped this FK",
                "last_step": "request_decision_skip"
            }
        else:
            # user_choice is index (1-5)
            try:
                idx = int(user_choice) - 1
                if idx < 0 or idx >= len(state["candidates"]):
                    logger.error(f"Invalid choice index: {idx} (candidates: {len(state['candidates'])})")
                    print(f"[ERROR] Invalid choice: {user_choice}")
                    return {
                        **state,
                        "chosen_table": "[SKIPPED]",
                        "chosen_score": None,
                        "decision_type": "skipped",
                        "notes": f"Invalid choice: {user_choice}",
                        "last_step": "request_decision_invalid"
                    }

                chosen_table, chosen_score = state["candidates"][idx]
                logger.info(f"User selected: {chosen_table} (score: {chosen_score:.3f})")
                print(f"[PASS] User selected: {chosen_table}")
                return {
                    **state,
                    "chosen_table": chosen_table,
                    "chosen_score": chosen_score,
                    "decision_type": "manual",
                    "notes": f"User selected option {user_choice}",
                    "last_step": "request_decision_manual"
                }
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to process user choice '{user_choice}': {e}")
                logger.debug(traceback.format_exc())
                print(f"[ERROR] Invalid input: {user_choice}")
                return {
                    **state,
                    "chosen_table": "[SKIPPED]",
                    "chosen_score": None,
                    "decision_type": "skipped",
                    "notes": f"Invalid input: {user_choice}",
                    "last_step": "request_decision_error"
                }

    except GraphInterrupt:
        # Re-raise GraphInterrupt - this is normal LangGraph behavior
        # The first time interrupt() is called, it raises this exception to pause execution
        raise
    except Exception as e:
        logger.error(f"[request_decision] Unexpected error: {e}", exc_info=True)
        print(f"[ERROR] Failed to process decision: {e}")
        return {
            **state,
            "chosen_table": "[SKIPPED]",
            "chosen_score": None,
            "decision_type": "skipped",
            "notes": f"Error: {str(e)}",
            "last_step": "request_decision_exception"
        }
