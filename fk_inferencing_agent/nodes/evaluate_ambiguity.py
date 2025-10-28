"""Evaluate ambiguity node - calculate score gap and decide routing."""

from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger
from rich.console import Console

logger = get_logger("fk_agent")
console = Console()


def evaluate_ambiguity_node(state: FKInferencingState) -> dict:
    """
    Calculate score gap between top 2 candidates.

    Args:
        state: Current workflow state

    Returns:
        Dict with score_gap
    """
    logger.info(f"[evaluate_ambiguity] Starting node (last_step: {state.get('last_step', 'unknown')})")

    candidates = state["candidates"]

    # Calculate score gap
    # Note: Chroma uses distance scores (lower is better), so we reverse the calculation
    if len(candidates) >= 2:
        score_gap = candidates[1][1] - candidates[0][1]  # second_best - best (positive when clear winner)
    elif len(candidates) == 1:
        score_gap = 1.0  # Only one candidate, clear winner
    else:
        score_gap = 0.0  # No candidates

    threshold = state["threshold"]
    logger.info(f"[evaluate_ambiguity] Score gap: {score_gap:.3f}, threshold: {threshold}")

    if score_gap >= threshold:
        console.print(f"\n✅ [bold green]Score gap: {score_gap:.3f}[/bold green] (>= {threshold} threshold)")
    else:
        console.print(f"\n⚠️  [bold yellow]Score gap: {score_gap:.3f}[/bold yellow] (< {threshold} threshold)")

    return {
        **state,
        "score_gap": score_gap,
        "last_step": "evaluate_ambiguity"
    }
