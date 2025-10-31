"""Finalize node - print summary statistics and complete."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import get_statistics
from utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable

logger = get_logger("fk_agent")
console = Console()


def finalize_node(state: FKInferencingState) -> dict:
    """
    Print summary statistics and complete workflow.

    Args:
        state: Current workflow state

    Returns:
        Empty dict
    """
    logger.info(f"[finalize] Starting node (last_step: {state.get('last_step', 'unknown')})")

    # Get statistics from Excel
    stats = get_statistics(state["excel_path"])

    # Create summary statistics table
    stats_table = RichTable(
        title="📊 FK Inferencing Summary",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan"
    )
    stats_table.add_column("📋 Metric", style="cyan", no_wrap=True)
    stats_table.add_column("🔢 Count", justify="right", style="bold white", width=10)

    # Add rows with color coding
    stats_table.add_row("Total ID columns", f"[bold]{stats['total']}[/bold]")
    stats_table.add_row("⚡ Auto-selected", f"[green]{stats.get('auto', 0)}[/green]")
    stats_table.add_row("👤 Manual selection", f"[cyan]{stats.get('manual', 0)}[/cyan]")
    stats_table.add_row("✅ Existing FKs", f"[blue]{stats.get('existing', 0)}[/blue]")
    stats_table.add_row("⏭️  Skipped", f"[yellow]{stats.get('skipped', 0)}[/yellow]")
    stats_table.add_row("⏸️  Incomplete", f"[dim]{stats.get('incomplete', 0)}[/dim]")

    console.print()
    console.print(stats_table)
    console.print(f"\n📄 [cyan]Excel file:[/cyan] {state['excel_path']}")

    if state.get("user_quit"):
        console.print()
        console.print(Panel(
            "[bold yellow]Session ended by user - progress saved\nRun again to resume from where you left off[/bold yellow]",  # noqa: E501
            title="⚠️  [yellow]Session Interrupted[/yellow]",
            border_style="yellow",
            padding=(1, 2)
        ))
        logger.info("[finalize] Session ended by user")
    else:
        console.print()
        console.print(Panel(
            "[bold green]🎉 All FK inferences complete![/bold green]",
            title="✅ [green]Success[/green]",
            border_style="green",
            padding=(1, 2)
        ))
        logger.info("[finalize] FK inferencing complete")

    return {
        **state,
        "last_step": "finalize"
    }
