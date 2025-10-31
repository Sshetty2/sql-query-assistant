"""Find candidates node - run vector search for FK candidates."""

from langgraph.types import RunnableConfig
from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import write_candidates
from database.infer_foreign_keys import find_candidate_tables
from utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable

logger = get_logger("fk_agent")
console = Console()


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
        logger.info(
            f"[find_candidates] Starting node (last_step: {state.get('last_step', 'unknown')})"
        )
        logger.info(
            f"Processing: {state['current_table']}.{state['current_column']} (base: {state['current_base_name']}"
        )

        # Check if this is a primary key and should be auto-skipped
        is_pk = state.get("current_is_pk", False)
        skip_pks = state.get("skip_primary_keys", False)

        # Display processing header with Rich Panel
        info_grid = RichTable.grid(padding=(0, 2))
        info_grid.add_column(style="cyan", justify="right")
        info_grid.add_column(style="bold white")
        info_grid.add_row(
            "Processing:", f"{state['current_table']}.{state['current_column']}"
        )
        info_grid.add_row("Base name:", state["current_base_name"])
        info_grid.add_row("Primary Key:", "🔑 YES" if is_pk else "❌ NO")

        console.print()
        console.print(
            Panel(
                info_grid,
                title="🎯 [bold blue]Finding FK Candidates[/bold blue]",
                title_align="left",
                border_style="blue",
            )
        )

        # Auto-skip if this is a primary key and skip flag is set
        if is_pk and skip_pks:
            console.print("🔑 [bold yellow]Auto-skipping primary key column[/bold yellow]")
            logger.info(f"Auto-skipping primary key: {state['current_table']}.{state['current_column']}")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "Auto-skipped (primary key)",
                "last_step": "find_candidates_pk_skipped",
            }

        # Get vector store from config
        vector_store = config.get("configurable", {}).get("vector_store")
        if not vector_store:
            logger.error("[find_candidates] Vector store not found in config")
            console.print(
                "❌ [bold red]Vector store not available in config[/bold red]"
            )
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "Vector store not available",
                "last_step": "find_candidates_no_vector_store",
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
            logger.error(
                f"[find_candidates] Failed to find candidates: {e}", exc_info=True
            )
            console.print(f"❌ [bold red]Failed to find candidates:[/bold red] {e}")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": f"Search error: {str(e)}",
                "last_step": "find_candidates_search_error",
            }

        if not raw_candidates:
            logger.warning(
                f"No candidates found for {state['current_table']}.{state['current_column']}"
            )
            console.print(
                "⚠️  [bold yellow]No candidates found - will skip this FK[/bold yellow]"
            )
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
                "last_step": "find_candidates_none",
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
            logger.error(
                f"[find_candidates] Failed to extract candidate table names: {e}",
                exc_info=True,
            )
            logger.debug(f"raw_candidates: {raw_candidates}")
            console.print(f"❌ [bold red]Failed to process candidates:[/bold red] {e}")
            return {
                **state,
                "candidates": [],
                "score_gap": 0.0,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": f"Candidate processing error: {str(e)}",
                "last_step": "find_candidates_extract_error",
            }

        # Write candidates to Excel
        try:
            write_candidates(state["excel_path"], state["current_row_idx"], candidates)
        except Exception as e:
            logger.error(f"Failed to write candidates to Excel: {e}", exc_info=True)
            console.print(
                f"⚠️  [bold yellow]Failed to write candidates to Excel:[/bold yellow] {e}"
            )

        # Display candidates in Rich Table
        candidates_table = RichTable(
            title="📊 Top Candidates",
            title_style="bold cyan",
            show_header=True,
            header_style="bold magenta",
            border_style="cyan",
        )
        candidates_table.add_column(
            "🏆 Rank", justify="center", style="bold yellow", width=8
        )
        candidates_table.add_column("📋 Table Name", style="bold white", no_wrap=True)
        candidates_table.add_column("🎯 Score", justify="right", style="cyan", width=10)
        candidates_table.add_column("📈 Similarity", width=20)

        for i, (table, score) in enumerate(candidates[:10], 1):
            # Color code based on score (lower is better for Chroma distance)
            if score < 0.3:
                score_color = "bold green"
                bar_char = "█"
            elif score < 0.5:
                score_color = "yellow"
                bar_char = "▓"
            else:
                score_color = "red"
                bar_char = "░"

            # Create visual bar (inverse of score, since lower is better)
            bar_length = int((1 - min(score, 1.0)) * 15)
            visual_bar = f"[{score_color}]{bar_char * bar_length}[/{score_color}]"

            candidates_table.add_row(
                f"{i}", table, f"[{score_color}]{score:.3f}[/{score_color}]", visual_bar
            )

        console.print()
        console.print(candidates_table)
        console.print()

        logger.info(
            f"[find_candidates] Found {len(candidates)} candidates successfully"
        )
        return {**state, "candidates": candidates, "last_step": "find_candidates"}

    except Exception as e:
        logger.error(f"[find_candidates] Unexpected error: {e}", exc_info=True)
        console.print(
            f"❌ [bold red]Unexpected error finding candidates:[/bold red] {e}"
        )
        return {
            **state,
            "candidates": [],
            "score_gap": 0.0,
            "chosen_table": "[SKIPPED]",
            "chosen_score": None,
            "decision_type": "skipped",
            "notes": f"Unexpected error: {str(e)}",
            "last_step": "find_candidates_exception",
        }
