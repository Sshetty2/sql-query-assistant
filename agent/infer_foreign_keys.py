"""Workflow node for foreign key inference."""

import os
from dotenv import load_dotenv

from agent.state import State
from database.infer_foreign_keys import infer_foreign_keys
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


def infer_foreign_keys_node(state: State) -> State:
    """
    Infer foreign keys for filtered schema tables.

    This node:
    - Only runs if INFER_FOREIGN_KEYS=true in environment
    - Works on state["filtered_schema"] (already filtered to 6-10 tables)
    - Augments existing foreign keys with inferred ones
    - Adds metadata: "inferred": True and "confidence": score

    Args:
        state: Current workflow state with filtered_schema

    Returns:
        Updated state with augmented filtered_schema
    """
    # Check if FK inference is enabled
    if not os.getenv("INFER_FOREIGN_KEYS", "false").lower() == "true":
        logger.info("Foreign key inference disabled (INFER_FOREIGN_KEYS=false), skipping")
        return {**state, "last_step": "infer_foreign_keys_skipped"}

    filtered_schema = state.get("filtered_schema", [])

    if not filtered_schema:
        logger.warning("No filtered schema available for FK inference")
        return {**state, "last_step": "infer_foreign_keys_no_schema"}

    logger.info(
        f"Starting FK inference for {len(filtered_schema)} filtered tables",
        extra={
            "filtered_table_count": len(filtered_schema),
            "filtered_tables": [t.get("table_name") for t in filtered_schema]
        }
    )

    # Get configuration from environment
    confidence_threshold = float(os.getenv("FK_INFERENCE_CONFIDENCE_THRESHOLD", "0.6"))
    top_k = int(os.getenv("FK_INFERENCE_TOP_K", "3"))

    logger.info(
        "FK inference configuration",
        extra={
            "confidence_threshold": confidence_threshold,
            "top_k": top_k
        }
    )

    # Run FK inference
    try:
        with log_execution_time(logger, "infer_foreign_keys_execution"):
            augmented_schema = infer_foreign_keys(
                filtered_schema=filtered_schema,
                confidence_threshold=confidence_threshold,
                top_k=top_k
            )

        # Calculate statistics
        total_fks = sum(len(table.get("foreign_keys", [])) for table in augmented_schema)
        inferred_fks = sum(
            len([fk for fk in table.get("foreign_keys", []) if fk.get("inferred")])
            for table in augmented_schema
        )
        existing_fks = total_fks - inferred_fks

        tables_with_inferred_fks = [
            table["table_name"]
            for table in augmented_schema
            if any(fk.get("inferred") for fk in table.get("foreign_keys", []))
        ]

        logger.info(
            "FK inference completed successfully",
            extra={
                "filtered_table_count": len(augmented_schema),
                "total_foreign_keys": total_fks,
                "existing_fks": existing_fks,
                "inferred_fks": inferred_fks,
                "tables_with_inferred_fks": tables_with_inferred_fks,
                "confidence_threshold": confidence_threshold
            }
        )

        # Debug: Save inference results
        from utils.debug_utils import save_debug_file
        save_debug_file(
            "inferred_foreign_keys.json",
            {
                "user_query": state.get("user_question", ""),
                "filtered_tables": [t["table_name"] for t in augmented_schema],
                "configuration": {
                    "confidence_threshold": confidence_threshold,
                    "top_k": top_k
                },
                "statistics": {
                    "total_foreign_keys": total_fks,
                    "existing_fks": existing_fks,
                    "inferred_fks": inferred_fks
                },
                "inferred_fks_detail": [
                    {
                        "table": table["table_name"],
                        "inferred_fks": [
                            {
                                "foreign_key": fk["foreign_key"],
                                "primary_key_table": fk["primary_key_table"],
                                "primary_key_column": fk.get("primary_key_column"),
                                "confidence": fk.get("confidence")
                            }
                            for fk in table.get("foreign_keys", [])
                            if fk.get("inferred")
                        ]
                    }
                    for table in augmented_schema
                    if any(fk.get("inferred") for fk in table.get("foreign_keys", []))
                ]
            },
            step_name="infer_foreign_keys",
            include_timestamp=True
        )

        return {
            **state,
            "filtered_schema": augmented_schema,
            "last_step": "infer_foreign_keys"
        }

    except Exception as e:
        logger.error(
            f"FK inference failed: {str(e)}",
            exc_info=True,
            extra={"error": str(e)}
        )
        # On error, return original state without modifications
        return {
            **state,
            "last_step": "infer_foreign_keys_error"
        }
