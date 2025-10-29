"""Load next row node - find next incomplete row from Excel."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import find_next_incomplete_row, load_row_data
from utils.logger import get_logger

logger = get_logger("fk_agent")


def load_next_row_node(state: FKInferencingState) -> dict:
    """
    Load next incomplete row from Excel.

    Args:
        state: Current workflow state

    Returns:
        Dict with current_row_idx, current_table, current_column, current_base_name, has_next_row
        Also resets decision fields for the new FK
    """
    logger.info(f"[load_next_row] Starting node (last_step: {state.get('last_step', 'unknown')})")

    row_idx = find_next_incomplete_row(state["excel_path"])

    if not row_idx:
        # All rows complete
        logger.info("[load_next_row] All rows completed")
        print("\n[PASS] All rows completed!")
        return {
            **state,
            "has_next_row": False,
            "current_row_idx": None,
            "last_step": "load_next_row_complete"
        }

    # Load row data
    row_data = load_row_data(state["excel_path"], row_idx)

    # Increment processed count
    processed_count = state.get("processed_count", 0) + 1

    is_pk = row_data.get("is_pk", False)
    logger.info(f"[load_next_row] Loaded row {row_idx}: {row_data['table_name']}.{row_data['fk_column']} (is_pk: {is_pk})")

    # IMPORTANT: Reset decision fields for new FK
    return {
        **state,
        "current_row_idx": row_idx,
        "current_table": row_data["table_name"],
        "current_column": row_data["fk_column"],
        "current_base_name": row_data["base_name"],
        "current_is_pk": is_pk,
        "has_next_row": True,
        "processed_count": processed_count,
        # Reset decision fields
        "candidates": [],
        "score_gap": 0.0,
        "chosen_table": None,
        "chosen_score": None,
        "decision_type": None,
        "notes": "",
        "last_step": "load_next_row"
    }
