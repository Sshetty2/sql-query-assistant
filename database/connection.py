"""Database connection utilities."""

import os
import pyodbc
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv

sample_db_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "sample-db.db"
)


def build_connection_string():
    """Build and return the connection string based on environment variables."""
    load_dotenv()

    if os.getenv("USE_TEST_DB", "").lower() == "true":
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


def get_db_connection():
    """Get a SQLDatabase instance using the appropriate connection string."""
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        # Use connect_args to pass check_same_thread=False to SQLite
        # This allows the connection to be used across threads in LangGraph workflows
        return SQLDatabase.from_uri(
            f"sqlite:///{sample_db_path}",
            engine_args={"connect_args": {"check_same_thread": False}}
        )

    connection_string = build_connection_string()
    return SQLDatabase.from_uri(f"mssql+pyodbc:///?odbc_connect={connection_string}")


def get_pyodbc_connection():
    """Get a raw database connection using the appropriate connection string."""
    connection_string = build_connection_string()
    if os.getenv("USE_TEST_DB", "").lower() == "true":
        import sqlite3

        # Allow SQLite connection to be used across threads
        # This is necessary because LangGraph may execute workflow nodes in different threads
        # check_same_thread=False is safe here because:
        # 1. We're not doing concurrent writes (single workflow execution)
        # 2. Connection is managed by workflow state machine
        # 3. Proper cleanup is enforced in cleanup node
        return sqlite3.connect(connection_string, check_same_thread=False)
    return pyodbc.connect(connection_string)


def init_database():
    """Initialize the database connection."""
    return get_db_connection()
