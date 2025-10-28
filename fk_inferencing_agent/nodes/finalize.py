"""Finalize node - print summary statistics and complete."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import get_statistics
from utils.logger import get_logger

logger = get_logger("fk_agent")


def finalize_node(state: FKInferencingState) -> dict:
    """
    Print summary statistics and complete workflow.

    Args:
        state: Current workflow state

    Returns:
        Empty dict
    """
    logger.info(f"[finalize] Starting node (last_step: {state.get('last_step', 'unknown')})")

    print("\n" + "="*60)
    print("FK INFERENCING SUMMARY")
    print("="*60)

    # Get statistics from Excel
    stats = get_statistics(state["excel_path"])

    print(f"Total ID columns:  {stats['total']}")
    print(f"Auto-selected:     {stats.get('auto', 0)}")
    print(f"Manual selection:  {stats.get('manual', 0)}")
    print(f"Existing FKs:      {stats.get('existing', 0)}")
    print(f"Skipped:           {stats.get('skipped', 0)}")
    print(f"Incomplete:        {stats.get('incomplete', 0)}")
    print(f"\nExcel file: {state['excel_path']}")

    if state.get("user_quit"):
        print("\n[WARN] Session ended by user - progress saved")
        print("Run again to resume from where you left off")
        logger.info("[finalize] Session ended by user")
    else:
        print("\n[PASS] FK inferencing complete!")
        logger.info("[finalize] FK inferencing complete")

    return {
        **state,
        "last_step": "finalize"
    }
