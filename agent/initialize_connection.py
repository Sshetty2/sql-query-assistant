"""Initialize database connection for the workflow."""

from agent.state import State
from database.connection import get_pyodbc_connection
from utils.logger import get_logger
from utils.stream_utils import emit_node_status, log_and_stream

logger = get_logger()


def initialize_connection(state: State):
    """
    Initialize database connection and add to state.

    This node creates the database connection once at the start of the workflow.
    The connection is then passed through state to all nodes that need it.
    It will be closed in the cleanup node.

    Args:
        state: Current workflow state

    Returns:
        Updated state with db_connection field set
    """
    emit_node_status("initialize_connection", "running", "Initializing database connection")

    log_and_stream(logger, "initialize_connection", "Creating database connection")

    try:
        db_connection = get_pyodbc_connection()

        log_and_stream(
            logger,
            "initialize_connection",
            "Database connection created successfully",
            extra={"connection_type": type(db_connection).__name__}
        )

        emit_node_status("initialize_connection", "completed")

        return {
            **state,
            "db_connection": db_connection,
            "last_step": "initialize_connection",
        }
    except Exception as e:
        log_and_stream(
            logger,
            "initialize_connection",
            f"Error creating database connection: {str(e)}",
            level="error",
            exc_info=True
        )
        emit_node_status("initialize_connection", "error")

        return {
            **state,
            "db_connection": None,
            "last_step": "initialize_connection",
        }
