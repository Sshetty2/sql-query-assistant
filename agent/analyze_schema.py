"""Retrieve schema information for the database."""

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from domain_specific_guidance.domain_specific_schema_callback import combine_schema
from database.introspection import introspect_schema, validate_schema_structure
from agent.state import State
from utils.logger import get_logger, log_execution_time
from utils.stream_utils import emit_node_status, log_and_stream

load_dotenv()
logger = get_logger()


def analyze_schema(state: State):
    """
    Retrieve comprehensive schema information using SQLAlchemy introspection.

    This extracts:
    - Table names
    - Column names, types, and nullability
    - Primary keys
    - Foreign key relationships
    - Additional metadata from domain-specific files (if available)

    Args:
        state: Current workflow state (includes db_connection)

    Returns:
        Updated state with schema information
    """
    # Get connection from state
    db_connection = state.get("db_connection")
    if not db_connection:
        log_and_stream(
            logger,
            "analyze_schema",
            "No database connection available in state",
            level="error"
        )
        emit_node_status("analyze_schema", "error")
        return {
            **state,
            "messages": [AIMessage(content="Error: No database connection available")],
            "last_step": "analyze_schema",
        }
    # Emit status update for streaming
    emit_node_status("analyze_schema", "running", "Analyzing database schema")

    log_and_stream(logger, "analyze_schema", "Starting SQLAlchemy-based schema analysis")

    try:
        # Use SQLAlchemy Inspector for dialect-agnostic introspection
        with log_execution_time(logger, "introspect_schema"):
            schema = introspect_schema(db_connection)

        # Validate structure matches schema_model.py
        validate_schema_structure(schema)

        log_and_stream(
            logger,
            "analyze_schema",
            f"Retrieved schema with {len(schema)} tables",
            extra={
                "table_count": len(schema),
                "total_columns": sum(len(t["columns"]) for t in schema),
                "total_foreign_keys": sum(len(t.get("foreign_keys", [])) for t in schema)
            }
        )

        # Combine with domain-specific metadata (if available)
        with log_execution_time(logger, "combine_schema_with_metadata"):
            combined_schema_with_metadata = combine_schema(schema)

        # Debug: Save combined schema with metadata
        from utils.debug_utils import save_debug_file
        save_debug_file(
            "combined_schema_with_metadata.json",
            combined_schema_with_metadata,
            step_name="analyze_schema"
        )

        log_and_stream(
            logger,
            "analyze_schema",
            "Schema analysis completed",
            extra={
                "table_count": len(combined_schema_with_metadata),
                "has_metadata": any(
                    "metadata" in table for table in combined_schema_with_metadata
                ),
                "has_foreign_keys": any(
                    "foreign_keys" in table for table in combined_schema_with_metadata
                ),
            },
        )

        emit_node_status("analyze_schema", "completed")

        return {
            **state,
            "messages": [AIMessage(content="Schema information gathered.")],
            "schema": combined_schema_with_metadata,
            "last_step": "analyze_schema",
        }
    except Exception as e:
        log_and_stream(logger, "analyze_schema", f"Error retrieving schema: {str(e)}", level="error", exc_info=True)
        emit_node_status("analyze_schema", "error")
        return {
            **state,
            "messages": [AIMessage(content=f"Error retrieving schema: {e}")],
            "last_step": "analyze_schema",
        }
