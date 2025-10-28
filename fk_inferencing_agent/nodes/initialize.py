"""Initialize node - introspect schema, create Excel, build vector store."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import create_excel
from database.connection import get_pyodbc_connection
from database.introspection import introspect_schema
from database.infer_foreign_keys import detect_id_columns, get_embedding_model
from utils.logger import get_logger

logger = get_logger("fk_agent")


def initialize_node(state: FKInferencingState) -> dict:
    """
    Initialize: introspect schema, create Excel (if needed), build vector store.

    Args:
        state: Current workflow state

    Returns:
        Dict with schema, vector_store, total_rows
    """
    import os

    logger.info(f"[initialize] Starting node (last_step: {state.get('last_step', 'unknown')})")

    print(f"\n[Step 1] Connecting to database: {state['database_name']}")

    # Connect and introspect
    conn = get_pyodbc_connection()
    schema = introspect_schema(conn)
    conn.close()

    print(f"[PASS] Introspected {len(schema)} tables")

    # Detect all ID columns
    print(f"\n[Step 2] Detecting ID columns...")
    all_id_columns = []
    existing_fks = {}

    for table in schema:
        table_name = table["table_name"]
        id_cols = detect_id_columns(table)
        all_id_columns.extend([(table_name, col, base) for col, base in id_cols])
        existing_fks[table_name] = table.get("foreign_keys", [])

    print(f"[PASS] Found {len(all_id_columns)} ID columns")

    # Create Excel with pre-populated rows (only if doesn't exist)
    if not os.path.exists(state["excel_path"]):
        print(f"\n[Step 3] Creating Excel audit file...")
        create_excel(state["excel_path"], all_id_columns, existing_fks)
    else:
        print(f"\n[Step 3] Excel file already exists, skipping creation")

    # Note: We don't build or store vector_store here to avoid serialization issues
    # It will be built on-demand in find_candidates_node
    print(f"\n[Step 4] Schema ready for vector search (vector store will be built on-demand)")

    print(f"\n[PASS] Initialization complete\n")

    logger.info(f"[initialize] Completed - {len(schema)} tables, {len(all_id_columns)} ID columns")

    return {
        **state,
        "schema": schema,
        "total_rows": len(all_id_columns),
        "last_step": "initialize"
    }
