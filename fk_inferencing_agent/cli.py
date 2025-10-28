#!/usr/bin/env python3
"""
FK Inferencing Agent CLI

Interactive foreign key mapping generator with human-in-the-loop.

Usage:
    python -m fk_inferencing_agent.cli
    python -m fk_inferencing_agent.cli --database mydb --threshold 0.15
"""

import argparse
import os
import traceback
from dotenv import load_dotenv
from langgraph.types import Command

from fk_inferencing_agent.create_agent import create_fk_inferencing_agent
from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger

load_dotenv()
logger = get_logger("fk_agent")


def get_user_choice() -> str:
    """
    Get and validate user input.

    Returns:
        User choice: '1'-'5', 's', or 'q'
    """
    while True:
        choice = input("\nYour choice: ").strip().lower()
        if choice in ["q", "s"] or (choice.isdigit() and 1 <= int(choice) <= 5):
            return choice
        print("[WARN] Invalid choice. Try again.")


def main():
    """Main CLI entry point."""
    try:
        parser = argparse.ArgumentParser(
            description="Interactive FK Inferencing Agent",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  python -m fk_inferencing_agent.cli
  python -m fk_inferencing_agent.cli --database mydb
  python -m fk_inferencing_agent.cli --threshold 0.15 --top-k 5
            """,
        )
        parser.add_argument(
            "--database", help="Database name (default: from .env DB_NAME)"
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=0.10,
            help="Score gap threshold for auto-selection (default: 0.10)",
        )
        parser.add_argument(
            "--top-k",
            type=int,
            default=5,
            help="Number of candidates to consider (default: 5)",
        )
        args = parser.parse_args()

        # Configuration
        database_name = args.database or os.getenv("DB_NAME", "unknown")
        excel_path = f"fk_mappings_{database_name}.xlsx"

        logger.info(f"Starting FK Inferencing Agent for database: {database_name}")
        logger.info(f"Configuration - threshold: {args.threshold}, top_k: {args.top_k}")

        # Initial state (vector_store is passed via context, not in state)
        initial_state: FKInferencingState = {
            "database_name": database_name,
            "threshold": args.threshold,
            "top_k": args.top_k,
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
        try:
            agent = create_fk_inferencing_agent()
            logger.info("FK Inferencing Agent workflow created successfully")
        except Exception as e:
            logger.error(f"Failed to create FK Inferencing Agent: {e}")
            logger.debug(traceback.format_exc())
            print(f"\n[ERROR] Failed to create agent: {e}")
            return 1

        # Thread ID and context (vector_store passed via configurable to avoid serialization)
        config = {
            "configurable": {"thread_id": database_name},
            "recursion_limit": 10000,
        }

        print("=" * 60)
        print("FK INFERENCING AGENT")
        print("=" * 60)
        print(f"Database:  {database_name}")
        print(f"Threshold: {args.threshold}")
        print(f"Top-K:     {args.top_k}")
        print("=" * 60)

        # Build vector store once before workflow (avoids serialization issues)
        print("\n[INFO] Pre-building vector store...")
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
                collection_name=f"fk_inference_{database_name}"
            )
            logger.info(f"Built Chroma vector store with {len(schema)} tables")
            print(f"[PASS] Chroma vector store built with {len(schema)} tables\n")

            # Add vector store to config (not serialized, passed to nodes via config)
            config["configurable"]["vector_store"] = vector_store
        except Exception as e:
            logger.error(f"Failed to build vector store: {e}")
            logger.debug(traceback.format_exc())
            print(f"\n[ERROR] Failed to build vector store: {e}")
            print("[INFO] Check logs for details: logs/fk_agent.log")
            return 1

        # Stream execution with interrupts
        # Use a loop to handle multiple interrupts
        try:
            input_value = initial_state
            while True:
                interrupted = False

                for event in agent.stream(
                    input_value, config=config, stream_mode="updates"
                ):
                    # Check for interrupt
                    if "__interrupt__" in event:
                        interrupted = True
                        try:
                            # Get user input (prompt is shown by the request_decision node)
                            user_choice = get_user_choice()
                            logger.info(f"User selected choice: {user_choice}")

                            # Resume with user's choice by restarting stream with Command
                            input_value = Command(resume=user_choice)
                            break  # Exit inner loop to restart stream

                        except Exception as e:
                            logger.error(f"Error during interrupt handling: {e}")
                            logger.debug(traceback.format_exc())
                            print(f"\n[ERROR] Failed to process user input: {e}")
                            print("[INFO] Attempting to continue...")
                            # Skip this FK and continue
                            input_value = Command(resume="s")
                            break

                # If no interrupt occurred, workflow completed
                if not interrupted:
                    break

        except KeyboardInterrupt:
            logger.info("User interrupted with Ctrl+C")
            print("\n\n[WARN] Interrupted by user (Ctrl+C)")
            print(f"[INFO] Progress saved to: {excel_path}")
            print("[INFO] Run again to resume from where you left off")
            return 0

        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            logger.debug(traceback.format_exc())
            print(f"\n[ERROR] Workflow failed: {e}")
            print(f"[INFO] Partial progress saved to: {excel_path}")
            print("[INFO] Check logs for details: logs/fk_agent.log")
            return 1

        logger.info("FK Inferencing Agent completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Unexpected error in main(): {e}")
        logger.debug(traceback.format_exc())
        print(f"\n[ERROR] Unexpected error: {e}")
        print("[INFO] Check logs for details: logs/fk_agent.log")
        return 1


if __name__ == "__main__":
    main()
