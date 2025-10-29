"""Request decision node - interrupt workflow for human input."""

import traceback
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from fk_inferencing_agent.state import FKInferencingState
from utils.logger import get_logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

logger = get_logger("fk_agent")
console = Console()


def request_decision_node(state: FKInferencingState) -> dict:
    """
    Interrupt workflow and request human decision.

    This node uses LangGraph's interrupt() to pause execution
    and wait for user input from the CLI.

    Args:
        state: Current workflow state

    Returns:
        Dict with updated state (chosen_table, chosen_score, decision_type, notes, user_quit)
        Routing is handled by conditional edge based on user_quit flag
    """
    try:
        logger.info(f"[request_decision] Starting node (last_step: {state.get('last_step', 'unknown')})")
        logger.info(f"Requesting user decision for {state['current_table']}.{state['current_column']}")

        # Prepare interrupt data
        interrupt_data = {
            "table": state["current_table"],
            "column": state["current_column"],
            "base_name": state["current_base_name"],
            "candidates": [
                {"index": i+1, "table": t, "score": f"{s:.3f}"}
                for i, (t, s) in enumerate(state["candidates"][:5])
            ],
            "score_gap": state["score_gap"],
            "threshold": state["threshold"]
        }

        # Display decision prompt with Rich Panel
        prompt_text = Text()
        prompt_text.append("Choose an option:\n\n", style="bold white")
        prompt_text.append("  🔢 ", style="cyan")
        prompt_text.append("[1-5]", style="bold cyan")
        prompt_text.append("  Select candidate\n", style="white")
        prompt_text.append("  🔑 ", style="magenta")
        prompt_text.append("[p]", style="bold magenta")
        prompt_text.append("     Mark as Primary Key (skip)\n", style="white")
        prompt_text.append("  ⏭️  ", style="yellow")
        prompt_text.append("[s]", style="bold yellow")
        prompt_text.append("     Skip this FK\n", style="white")
        prompt_text.append("  🚪 ", style="red")
        prompt_text.append("[q]", style="bold red")
        prompt_text.append("     Quit and save", style="white")

        console.print()
        console.print(Panel(
            prompt_text,
            title="⚠️  [bold yellow]AMBIGUOUS MATCH - User Decision Required[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(1, 2)
        ))

        # Pause and wait for user input
        # This returns the value passed to Command(resume=...)
        user_choice = interrupt(interrupt_data)

        logger.info(f"Received user choice: {user_choice}")

        # Process user choice
        if user_choice == "q":
            logger.info("User chose to quit")
            console.print("🚪 [bold yellow]User quit session[/bold yellow]")
            return {
                **state,
                "user_quit": True,
                "chosen_table": None,
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "User quit session",
                "last_step": "request_decision_quit"
            }
        elif user_choice == "s":
            logger.info("User chose to skip")
            console.print("⏭️  [bold yellow]User skipped this FK[/bold yellow]")
            return {
                **state,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "User skipped this FK",
                "last_step": "request_decision_skip"
            }
        elif user_choice == "p":
            logger.info("User marked column as primary key")
            console.print("🔑 [bold magenta]User marked as Primary Key - skipping[/bold magenta]")
            return {
                **state,
                "chosen_table": "[SKIPPED]",
                "chosen_score": None,
                "decision_type": "skipped",
                "notes": "Marked as primary key by user",
                "last_step": "request_decision_pk"
            }
        else:
            # user_choice is index (1-5)
            try:
                idx = int(user_choice) - 1
                if idx < 0 or idx >= len(state["candidates"]):
                    logger.error(f"Invalid choice index: {idx} (candidates: {len(state['candidates'])})")
                    console.print(f"❌ [bold red]Invalid choice:[/bold red] {user_choice}")
                    return {
                        **state,
                        "chosen_table": "[SKIPPED]",
                        "chosen_score": None,
                        "decision_type": "skipped",
                        "notes": f"Invalid choice: {user_choice}",
                        "last_step": "request_decision_invalid"
                    }

                chosen_table, chosen_score = state["candidates"][idx]
                logger.info(f"User selected: {chosen_table} (score: {chosen_score:.3f})")
                console.print(f"✅ [bold green]User selected:[/bold green] {chosen_table}")
                return {
                    **state,
                    "chosen_table": chosen_table,
                    "chosen_score": chosen_score,
                    "decision_type": "manual",
                    "notes": f"User selected option {user_choice}",
                    "last_step": "request_decision_manual"
                }
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to process user choice '{user_choice}': {e}")
                logger.debug(traceback.format_exc())
                console.print(f"❌ [bold red]Invalid input:[/bold red] {user_choice}")
                return {
                    **state,
                    "chosen_table": "[SKIPPED]",
                    "chosen_score": None,
                    "decision_type": "skipped",
                    "notes": f"Invalid input: {user_choice}",
                    "last_step": "request_decision_error"
                }

    except GraphInterrupt:
        # Re-raise GraphInterrupt - this is normal LangGraph behavior
        # The first time interrupt() is called, it raises this exception to pause execution
        raise
    except Exception as e:
        logger.error(f"[request_decision] Unexpected error: {e}", exc_info=True)
        console.print(f"❌ [bold red]Failed to process decision:[/bold red] {e}")
        return {
            **state,
            "chosen_table": "[SKIPPED]",
            "chosen_score": None,
            "decision_type": "skipped",
            "notes": f"Error: {str(e)}",
            "last_step": "request_decision_exception"
        }
