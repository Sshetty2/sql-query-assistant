#!/usr/bin/env python3
"""
Interactive test for FK inferencing agent.
Tests a few rows with simulated input, then allows checking logs.
"""

import os
from dotenv import load_dotenv
from langgraph.types import Command

from fk_inferencing_agent.create_agent import create_fk_inferencing_agent
from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger

load_dotenv()
logger = get_logger("fk_agent_test")


def main():
    # Configuration
    database_name = os.getenv("DB_NAME", "unknown")
    excel_path = f"fk_mappings_{database_name}.xlsx"

    # Initial state (vector_store passed via context)
    initial_state: FKInferencingState = {
        "database_name": database_name,
        "threshold": 0.10,
        "top_k": 5,
        "excel_path": excel_path,
        "schema": [],
        "current_row_idx": None,
        "current_table": "",
        "current_column": "",
        "current_base_name": "",
        "candidates": [],
        "score_gap": 0.0,
        "chosen_table": None,
        "chosen_score": None,
        "decision_type": None,
        "notes": "",
        "has_next_row": True,
        "user_quit": False,
        "total_rows": 0,
        "processed_count": 0,
        "last_step": "start",
    }

    # Create agent
    agent = create_fk_inferencing_agent()
    config = {
        "configurable": {"thread_id": database_name},
        "recursion_limit": 1000,  # Allow up to 1000 node executions
    }

    print("=" * 60)
    print("FK INFERENCING AGENT INTERACTIVE TEST")
    print("=" * 60)
    print(f"Database:  {database_name}")
    print(f"Threshold: 0.10")
    print(f"Top-K:     5")
    print("=" * 60)
    print("\nThis test will process the first few rows interactively.")
    print("It will log detailed information to logs/fk_agent.log")
    print("=" * 60)

    # Build vector store before workflow
    print("\n[TEST] Building vector store...")
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
        from langchain_community.vectorstores.utils import filter_complex_metadata
        from database.connection import get_pyodbc_connection
        from database.introspection import introspect_schema
        from database.infer_foreign_keys import get_embedding_model

        conn = get_pyodbc_connection()
        schema = introspect_schema(conn)
        conn.close()

        embedding_model = get_embedding_model()
        docs = [
            Document(page_content=f"Table: {t['table_name']}", metadata=t)
            for t in schema
        ]
        # Filter complex metadata (Chroma only supports simple types)
        docs = filter_complex_metadata(docs)
        vector_store = Chroma.from_documents(
            docs,
            embedding_model,
            collection_name=f"fk_inference_test_{database_name}"
        )
        print(f"[TEST] Vector store built with {len(schema)} tables\n")

        # Add vector store to config
        config["configurable"]["vector_store"] = vector_store
    except Exception as e:
        print(f"[TEST ERROR] Failed to build vector store: {e}")
        logger.error(f"Failed to build vector store: {e}", exc_info=True)
        return 1

    # Process first 5 interrupts, then quit
    interrupt_count = 0
    max_interrupts = 5

    try:
        input_value = initial_state
        while True:
            interrupted = False

            for event in agent.stream(input_value, config=config, stream_mode="updates"):
                # Check for interrupt
                if "__interrupt__" in event:
                    interrupt_count += 1
                    interrupted = True

                    print(f"\n[TEST] Interrupt #{interrupt_count}/{max_interrupts}")

                    if interrupt_count < max_interrupts:
                        # Auto-select option 2 to test non-first choice
                        print("[TEST] Auto-selecting option 2\n")
                        logger.info(
                            f"Test auto-selecting option 2 for interrupt #{interrupt_count}"
                        )
                        input_value = Command(resume="2")
                        break  # Exit inner loop to restart stream
                    else:
                        # Quit after max_interrupts
                        print(f"[TEST] Reached {max_interrupts} interrupts, quitting\n")
                        logger.info(f"Test quitting after {max_interrupts} interrupts")
                        input_value = Command(resume="q")
                        break

            # If no interrupt or quit requested, exit
            if not interrupted or interrupt_count >= max_interrupts:
                break

        print("\n[TEST] Test completed successfully!")
        print(f"[TEST] Excel file: {excel_path}")
        print("[TEST] Log file: logs/fk_agent.log")
        return 0

    except Exception as e:
        print(f"\n[TEST ERROR] {type(e).__name__}: {e}")
        logger.error(f"Test failed: {e}", exc_info=True)
        print("[TEST] Check logs/fk_agent.log for details")
        return 1


if __name__ == "__main__":
    exit(main())
