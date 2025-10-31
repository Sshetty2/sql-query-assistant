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
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from rich.table import Table

from fk_inferencing_agent.create_agent import create_fk_inferencing_agent
from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger

load_dotenv()
logger = get_logger("fk_agent")

# Create Rich console for CLI output
console = Console()


def get_user_choice() -> str:
    """
    Get and validate user input.

    Returns:
        User choice: '1'-'5', 'p', 's', or 'q'
    """
    while True:
        choice = input("\nYour choice: ").strip().lower()
        if choice in ["q", "s", "p"] or (choice.isdigit() and 1 <= int(choice) <= 5):
            return choice
        console.print("⚠️  [bold yellow]Invalid choice. Try again.[/bold yellow]")


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
            default=10,
            help="Number of candidates to consider (default: 10)",
        )
        parser.add_argument(
            "--skip-primary-keys",
            action="store_true",
            default=True,
            help="Automatically skip columns that are primary keys (default: False)",
        )
        args = parser.parse_args()

        # Configuration
        database_name = args.database or os.getenv("DB_NAME", "unknown")
        excel_path = f"fk_mappings_{database_name}.xlsx"

        logger.info(f"Starting FK Inferencing Agent for database: {database_name}")
        logger.info(
            f"Configuration - threshold: {args.threshold}, top_k: {args.top_k}, skip_primary_keys: {args.skip_primary_keys}"  # noqa: E501
        )

        # Initial state (vector_store is passed via context, not in state)
        initial_state: FKInferencingState = {
            "database_name": database_name,
            "threshold": args.threshold,
            "top_k": args.top_k,
            "excel_path": excel_path,
            "skip_primary_keys": args.skip_primary_keys,
            "schema": [],
            "current_row_idx": None,
            "current_table": "",
            "current_column": "",
            "current_base_name": "",
            "current_is_pk": False,
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
            console.print(f"\n❌ [bold red]Failed to create agent:[/bold red] {e}")
            return 1

        # Thread ID and context (vector_store passed via configurable to avoid serialization)
        config = {
            "configurable": {"thread_id": database_name},
            "recursion_limit": 10000,
        }

        # Display header with Rich Panel
        config_table = Table.grid(padding=(0, 2))
        config_table.add_column(style="cyan", justify="right")
        config_table.add_column(style="bold white")
        config_table.add_row("Database:", database_name)
        config_table.add_row("Threshold:", str(args.threshold))
        config_table.add_row("Top-K:", str(args.top_k))
        config_table.add_row(
            "Skip PKs:", "✅ Yes" if args.skip_primary_keys else "❌ No"
        )

        console.print()
        console.print(
            Panel(
                config_table,
                title="🔍 [bold blue]FK INFERENCING AGENT[/bold blue]",
                title_align="left",
                border_style="blue",
                padding=(1, 2),
            )
        )
        console.print()

        # Build vector store once before workflow (avoids serialization issues)
        try:
            from langchain_chroma import Chroma
            from langchain_core.documents import Document
            from langchain_community.vectorstores.utils import filter_complex_metadata
            from database.connection import get_pyodbc_connection
            from database.introspection import introspect_schema
            from database.infer_foreign_keys import get_embedding_model

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("🔨 Building vector store...", total=4)

                # Step 1: Connect and introspect
                conn = get_pyodbc_connection()
                schema = introspect_schema(conn)
                conn.close()
                progress.update(task, advance=1, description="📊 Schema introspected")

                # Step 2: Get embedding model
                embedding_model = get_embedding_model()
                progress.update(
                    task, advance=1, description="🤖 Embedding model loaded"
                )

                # Step 3: Create documents
                docs = [
                    Document(page_content=f"Table: {t['table_name']}", metadata=t)
                    for t in schema
                ]
                docs = filter_complex_metadata(docs)
                progress.update(task, advance=1, description="📝 Documents created")

                # Step 4: Build vector store
                vector_store = Chroma.from_documents(
                    docs,
                    embedding_model,
                    collection_name=f"fk_inference_{database_name}",
                )
                progress.update(task, advance=1, description="✅ Vector store ready")

            logger.info(f"Built Chroma vector store with {len(schema)} tables")
            console.print(
                f"✅ [bold green]Vector store built with {len(schema)} tables[/bold green]\n"
            )

            # Add vector store to config (not serialized, passed to nodes via config)
            config["configurable"]["vector_store"] = vector_store
        except Exception as e:
            logger.error(f"Failed to build vector store: {e}")
            logger.debug(traceback.format_exc())
            console.print(
                f"\n❌ [bold red]Failed to build vector store:[/bold red] {e}"
            )
            console.print("📋 [cyan]Check logs for details:[/cyan] logs/fk_agent.log")
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
                            console.print(
                                f"\n❌ [bold red]Failed to process user input:[/bold red] {e}"
                            )
                            console.print("🔄 [cyan]Attempting to continue...[/cyan]")
                            # Skip this FK and continue
                            input_value = Command(resume="s")
                            break

                # If no interrupt occurred, workflow completed
                if not interrupted:
                    break

        except KeyboardInterrupt:
            logger.info("User interrupted with Ctrl+C")
            console.print(
                "\n\n⚠️  [bold yellow]Interrupted by user (Ctrl+C)[/bold yellow]"
            )
            console.print(f"💾 [green]Progress saved to:[/green] {excel_path}")
            console.print("🔄 [cyan]Run again to resume from where you left off[/cyan]")
            return 0

        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            logger.debug(traceback.format_exc())
            console.print(f"\n❌ [bold red]Workflow failed:[/bold red] {e}")
            console.print(
                f"💾 [yellow]Partial progress saved to:[/yellow] {excel_path}"
            )
            console.print("📋 [cyan]Check logs for details:[/cyan] logs/fk_agent.log")
            return 1

        logger.info("FK Inferencing Agent completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Unexpected error in main(): {e}")
        logger.debug(traceback.format_exc())
        console.print(f"\n❌ [bold red]Unexpected error:[/bold red] {e}")
        console.print("📋 [cyan]Check logs for details:[/cyan] logs/fk_agent.log")
        return 1


if __name__ == "__main__":
    main()
