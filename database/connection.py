"""Database connection utilities."""

import json
import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv

sample_db_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "sample-db.db"
)

_databases_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "databases")
_registry_path = os.path.join(_databases_dir, "registry.json")


def get_demo_db_path(db_id: str) -> str:
    """Resolve a demo database ID to its file path using the registry.

    Args:
        db_id: Database identifier (e.g. "demo_db_1", "demo_db_2").

    Returns:
        Absolute path to the SQLite database file.

    Raises:
        ValueError: If db_id is not found in the registry or file does not exist.
    """
    if not os.path.exists(_registry_path):
        raise ValueError(f"Database registry not found at {_registry_path}")

    with open(_registry_path, "r") as f:
        registry = json.load(f)

    for entry in registry:
        if entry["id"] == db_id:
            db_path = os.path.join(_databases_dir, entry["file"])
            # Prevent path traversal — ensure resolved path stays within databases dir
            if not os.path.realpath(db_path).startswith(os.path.realpath(_databases_dir)):
                raise ValueError(f"Invalid database path for {db_id}")
            if not os.path.exists(db_path):
                raise ValueError(f"Database file not found: {db_path}")
            return db_path

    raise ValueError(f"Unknown database ID: {db_id}")


def build_connection_string(db_id: str = None):
    """Build and return the connection string based on environment variables."""
    load_dotenv()

    if os.getenv("USE_TEST_DB", "").lower() == "true":
        if db_id:
            return get_demo_db_path(db_id)
        return sample_db_path

    connection_params = [
        "DRIVER={ODBC Driver 17 for SQL Server}",
        f"SERVER={os.getenv('DB_SERVER')}",
        f"DATABASE={os.getenv('DB_NAME')}",
    ]

    if os.getenv("DB_USER") and os.getenv("DB_PASSWORD"):
        connection_params.extend(
            [f"UID={os.getenv('DB_USER')}", f"PWD={os.getenv('DB_PASSWORD')}"]
        )
    else:
        connection_params.append("Trusted_Connection=yes")

    return ";".join(connection_params)


def get_db_connection(db_id: str = None):
    """Get a SQLDatabase instance using the appropriate connection string."""
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        db_path = get_demo_db_path(db_id) if db_id else sample_db_path
        # Use connect_args to pass check_same_thread=False to SQLite
        # This allows the connection to be used across threads in LangGraph workflows
        return SQLDatabase.from_uri(
            f"sqlite:///{db_path}",
            engine_args={"connect_args": {"check_same_thread": False}}
        )

    connection_string = build_connection_string()
    return SQLDatabase.from_uri(f"mssql+pyodbc:///?odbc_connect={connection_string}")


def get_pyodbc_connection(db_id: str = None):
    """Get a raw database connection using the appropriate connection string."""
    connection_string = build_connection_string(db_id)
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        import sqlite3

        # Allow SQLite connection to be used across threads
        # This is necessary because LangGraph may execute workflow nodes in different threads
        # check_same_thread=False is safe here because:
        # 1. We're not doing concurrent writes (single workflow execution)
        # 2. Connection is managed by workflow state machine
        # 3. Proper cleanup is enforced in cleanup node
        return sqlite3.connect(connection_string, check_same_thread=False)
    import pyodbc
    return pyodbc.connect(connection_string)


def init_database():
    """Initialize the database connection."""
    return get_db_connection()
