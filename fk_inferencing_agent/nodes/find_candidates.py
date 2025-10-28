"""Find candidates node - run vector search for FK candidates."""

import traceback
from typing import Any
from langgraph.types import RunnableConfig
from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import write_candidates
from database.infer_foreign_keys import find_candidate_tables
from utils.logger import get_logger

logger = get_logger("fk_agent")


def find_candidates_node(state: FKInferencingState, config: RunnableConfig) -> dict:
    """
    Run vector search to find FK candidates.

    Args:
        state: Current workflow state
        config: Runnable config containing vector_store in configurable

    Returns:
        Dict with candidates list
    """
    try:
        logger.info(f"[find_candidates] Starting node (last_step: {state.get('last_step', 'unknown')})")
        logger.info(
            f"Processing: {state['current_table']}.{state['current_column']} (base: {state['current_base_name']}"
        )

        print(f"\n{'='*60}")
        print(f"Processing: {state['current_table']}.{state['current_column']}")
        print(f"Base name: {state['current_base_name']}")
        print(f"{'='*60}")

        # Get vector store from config
        vector_store = config.get("configurable", {}).get("vector_store")
        if not vector_store:
            logger.error("[find_candidates] Vector store not found in config")
            print(f"[ERROR] Vector store not available in config")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "Vector store not available",
                "last_step": "find_candidates_no_vector_store"
            }

        # Find candidates using vector similarity
        try:
            raw_candidates = find_candidate_tables(
                base_name=state["current_base_name"],
                filtered_schema=state["schema"],
                vector_store=vector_store,
                source_table=state["current_table"],
                top_k=state["top_k"],
            )
        except Exception as e:
            logger.error(f"[find_candidates] Failed to find candidates: {e}", exc_info=True)
            print(f"[ERROR] Failed to find candidates: {e}")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": f"Search error: {str(e)}",
                "last_step": "find_candidates_search_error"
            }

        if not raw_candidates:
            logger.warning(
                f"No candidates found for {state['current_table']}.{state['current_column']}"
            )
            print("[WARN] No candidates found - will skip this FK")
            # Write to Excel
            write_candidates(state["excel_path"], state["current_row_idx"], [])
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "No candidates found",
                "last_step": "find_candidates_none"
            }

        # Extract table names from candidates (find_candidate_tables returns (table_dict, score) tuples)
        try:
            candidates = [
                (table_dict["table_name"], score)
                for table_dict, score in raw_candidates
            ]
            logger.info(
                f"Found {len(candidates)} candidates, top score: {candidates[0][1]:.3f}"
            )
        except Exception as e:
            logger.error(f"[find_candidates] Failed to extract candidate table names: {e}", exc_info=True)
            logger.debug(f"raw_candidates: {raw_candidates}")
            print(f"[ERROR] Failed to process candidates: {e}")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": f"Candidate processing error: {str(e)}",
                "last_step": "find_candidates_extract_error"
            }

        # Write candidates to Excel
        try:
            write_candidates(state["excel_path"], state["current_row_idx"], candidates)
        except Exception as e:
            logger.error(f"Failed to write candidates to Excel: {e}", exc_info=True)
            print(f"[WARN] Failed to write candidates to Excel: {e}")

        # Display candidates
        print("\nTop 5 Candidates:")
        for i, (table, score) in enumerate(candidates[:5], 1):
            print(f"  [{i}] {table:30s} (score: {score:.3f})")

        logger.info(f"[find_candidates] Found {len(candidates)} candidates successfully")
        return {
            **state,
            "candidates": candidates,
            "last_step": "find_candidates"
        }

    except Exception as e:
        logger.error(f"[find_candidates] Unexpected error: {e}", exc_info=True)
        print(f"[ERROR] Unexpected error finding candidates: {e}")
        return {
            **state,
            "candidates": [],
            "score_gap": 0.0,
            "chosen_table": "[SKIPPED]",
            "chosen_score": None,
            "decision_type": "skipped",
            "notes": f"Unexpected error: {str(e)}",
            "last_step": "find_candidates_exception"
        }
