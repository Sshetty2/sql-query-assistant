"""Initialize node - introspect schema, create Excel, build vector store."""

from fk_inferencing_agent.state import FKInferencingState
from fk_inferencing_agent.excel_manager import create_excel
from database.connection import get_pyodbc_connection
from database.introspection import introspect_schema
from database.infer_foreign_keys import detect_id_columns
from utils.logger import get_logger
from rich.console import Console

logger = get_logger("fk_agent")
console = Console()


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

    console.print(f"\n🔄 [bold cyan][Step 1][/bold cyan] Connecting to database: [white]{state['database_name']}[/white]")  # noqa: E501

    # Connect and introspect
    conn = get_pyodbc_connection()
    schema = introspect_schema(conn)
    conn.close()

    console.print(f"✅ [bold green]Introspected {len(schema)} tables[/bold green]")

    # Detect all ID columns
    console.print("\n🔄 [bold cyan][Step 2][/bold cyan] Detecting ID columns...")
    all_id_columns = []
    existing_fks = {}

    for table in schema:
        table_name = table["table_name"]
        id_cols = detect_id_columns(table)
        all_id_columns.extend([(table_name, col, base, is_pk) for col, base, is_pk in id_cols])
        existing_fks[table_name] = table.get("foreign_keys", [])

    console.print(f"✅ [bold green]Found {len(all_id_columns)} ID columns[/bold green]")

    # Create Excel with pre-populated rows (only if doesn't exist)
    if not os.path.exists(state["excel_path"]):
        console.print("\n🔄 [bold cyan][Step 3][/bold cyan] Creating Excel audit file...")
        create_excel(state["excel_path"], all_id_columns, existing_fks)
    else:
        console.print("\n📄 [cyan][Step 3][/cyan] Excel file already exists, skipping creation")

    # Note: We don't build or store vector_store here to avoid serialization issues
    # It will be built on-demand in find_candidates_node
    console.print("\n🔄 [bold cyan][Step 4][/bold cyan] Schema ready for vector search")

    console.print("\n✅ [bold green]Initialization complete[/bold green]\n")

    logger.info(f"[initialize] Completed - {len(schema)} tables, {len(all_id_columns)} ID columns")

    return {
        **state,
        "schema": schema,
        "total_rows": len(all_id_columns),
        "last_step": "initialize"
    }
