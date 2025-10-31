"""Retrieve schema information for the database."""

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from domain_specific_guidance.combine_json_schema import combine_schema
from database.introspection import introspect_schema, validate_schema_structure
from agent.state import State
from utils.logger import get_logger, log_execution_time

load_dotenv()
logger = get_logger()


def analyze_schema(state: State, db_connection):
    """
    Retrieve comprehensive schema information using SQLAlchemy introspection.

    This extracts:
    - Table names
    - Column names, types, and nullability
    - Primary keys
    - Foreign key relationships
    - Additional metadata from domain-specific files (if available)

    Args:
        state: Current workflow state
        db_connection: Database connection (pyodbc or sqlite3)

    Returns:
        Updated state with schema information
    """
    logger.info("Starting SQLAlchemy-based schema analysis")

    try:
        # Use SQLAlchemy Inspector for dialect-agnostic introspection
        with log_execution_time(logger, "introspect_schema"):
            schema = introspect_schema(db_connection)

        # Validate structure matches schema_model.py
        validate_schema_structure(schema)

        logger.info(
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

        logger.info(
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

        return {
            **state,
            "messages": [AIMessage(content="Schema information gathered.")],
            "schema": combined_schema_with_metadata,
            "last_step": "analyze_schema",
        }
    except Exception as e:
        logger.error(f"Error retrieving schema: {str(e)}", exc_info=True)
        return {
            **state,
            "messages": [AIMessage(content=f"Error retrieving schema: {e}")],
            "last_step": "analyze_schema",
        }
