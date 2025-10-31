"""Record decision node - write decision to Excel."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import write_decision
from utils.logger import get_logger
from rich.console import Console

logger = get_logger("fk_agent")
console = Console()


def record_decision_node(state: FKInferencingState) -> dict:
    """
    Write decision to Excel row.

    Args:
        state: Current workflow state

    Returns:
        Empty dict (updates handled via excel_manager)
    """
    try:
        logger.info(f"[record_decision] Starting node (last_step: {state.get('last_step', 'unknown')})")

        # Skip recording if no decision was made (e.g., no candidates)
        if not state.get("decision_type"):
            logger.warning("[record_decision] No decision_type found in state, skipping record")
            return {
                **state,
                "last_step": "record_decision_skipped"
            }

        # Prepare decision data
        decision = {
            "chosen_table": state["chosen_table"],
            "chosen_score": state["chosen_score"],
            "decision_type": state["decision_type"],
            "notes": state["notes"]
        }

        logger.info(f"[record_decision] Recording: {decision['chosen_table']} ({decision['decision_type']})")

        # Write to Excel
        try:
            write_decision(
                state["excel_path"],
                state["current_row_idx"],
                decision
            )
            logger.debug(f"[record_decision] Decision written to Excel row {state['current_row_idx']}")
        except Exception as e:
            logger.error(f"[record_decision] Failed to write decision to Excel: {e}", exc_info=True)
            console.print(f"❌ [bold red]Failed to save decision to Excel:[/bold red] {e}")
            # Continue despite error - decision is recorded in state

        return {
            **state,
            "last_step": "record_decision"
        }

    except Exception as e:
        logger.error(f"[record_decision] Unexpected error: {e}", exc_info=True)
        console.print(f"❌ [bold red]Failed to record decision:[/bold red] {e}")
        return {
            **state,
            "last_step": "record_decision_exception"
        }
