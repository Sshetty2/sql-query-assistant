"""Auto-select node - automatically select when score gap is clear."""

from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger

logger = get_logger("fk_agent")


def auto_select_node(state: FKInferencingState) -> dict:
    """
    Auto-select top candidate when score gap >= threshold.

    Args:
        state: Current workflow state

    Returns:
        Dict with chosen_table, chosen_score, decision_type, notes
    """
    logger.info(f"[auto_select] Starting node (last_step: {state.get('last_step', 'unknown')})")

    candidates = state["candidates"]
    score_gap = state["score_gap"]

    # Select top candidate
    chosen_table, chosen_score = candidates[0]

    logger.info(f"Auto-selected: {chosen_table} (score: {chosen_score:.3f}, gap: {score_gap:.3f})")
    print(f"[PASS] Auto-selected: {chosen_table}")

    return {
        **state,
        "chosen_table": chosen_table,
        "chosen_score": chosen_score,
        "decision_type": "auto",
        "notes": f"Gap: {score_gap:.3f} >= threshold",
        "last_step": "auto_select"
    }
