"""Dialect-agnostic database schema introspection using SQLAlchemy."""

import os
import re
from typing import List, Dict, Any
from sqlalchemy import inspect, create_engine
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()


def clean_data_type(data_type_str: str) -> str:
    """
    Clean up data type string by removing verbose clauses.

    Removes:
    - COLLATE clauses (e.g., COLLATE "SQL_Latin1_General_CP1_CI_AS")
    - Unnecessary whitespace
    - Other verbose type modifiers

    Args:
        data_type_str: Raw data type string from SQLAlchemy

    Returns:
        Cleaned data type string

    Examples:
        'NVARCHAR(100) COLLATE "SQL_Latin1_General_CP1_CI_AS"' -> 'NVARCHAR(100)'
        'VARCHAR(50) COLLATE "utf8_general_ci"' -> 'VARCHAR(50)'
        'DATETIME' -> 'DATETIME'
    """
    # Remove COLLATE clauses
    cleaned = re.sub(r'\s+COLLATE\s+"[^"]+"', '', data_type_str)
    cleaned = re.sub(r"\s+COLLATE\s+'[^']+'", '', cleaned)
    cleaned = re.sub(r'\s+COLLATE\s+\S+', '', cleaned)

    # Remove extra whitespace
    cleaned = ' '.join(cleaned.split())

    return cleaned.strip()


def get_engine_from_connection(connection):
    """
    Create SQLAlchemy engine from existing connection.

    Args:
        connection: pyodbc.Connection or sqlite3.Connection

    Returns:
        SQLAlchemy Engine instance
    """
    use_test_db = os.getenv("USE_TEST_DB", "").lower() == "true"

    if use_test_db:
        # SQLite test database
        sample_db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "sample-db.db"
        )
        return create_engine(f"sqlite:///{sample_db_path}")
    else:
        # SQL Server
        connection_params = [
            "DRIVER={ODBC Driver 17 for SQL Server}",
            f"SERVER={os.getenv('DB_SERVER')}",
            f"DATABASE={os.getenv('DB_NAME')}",
        ]

        if os.getenv("DB_USER") and os.getenv("DB_PASSWORD"):
            connection_params.extend([
                f"UID={os.getenv('DB_USER')}",
                f"PWD={os.getenv('DB_PASSWORD')}"
            ])
        else:
            connection_params.append("Trusted_Connection=yes")

        connection_string = ";".join(connection_params)
        return create_engine(f"mssql+pyodbc:///?odbc_connect={connection_string}")


def introspect_schema(connection) -> List[Dict[str, Any]]:
    """
    Use SQLAlchemy Inspector to extract comprehensive schema information.

    This is dialect-agnostic and works with SQLite, SQL Server, PostgreSQL, MySQL, etc.

    Args:
        connection: Database connection (pyodbc or sqlite3)

    Returns:
        List of table dictionaries with structure:
        [
            {
                "table_name": str,
                "columns": [
                    {
                        "column_name": str,
                        "data_type": str,
                        "is_nullable": bool
                    }
                ],
                "foreign_keys": [
                    {
                        "foreign_key": str,  # column in this table
                        "primary_key_table": str,  # referenced table
                        "primary_key_column": str  # referenced column
                    }
                ],
                "metadata": {
                    "primary_key": str  # primary key column name (if single-column PK)
                }
            }
        ]
    """
    logger.info("Starting SQLAlchemy-based schema introspection")

    engine = None
    try:
        # Create engine and inspector
        engine = get_engine_from_connection(connection)
        inspector = inspect(engine)

        # Get all table names
        table_names = inspector.get_table_names()
        logger.info(f"Found {len(table_names)} tables")

        schema = []

        for table_name in table_names:
            logger.debug(f"Introspecting table: {table_name}")

            # Get columns with full details
            columns_info = inspector.get_columns(table_name)
            columns = []

            for col in columns_info:
                # Extract column information
                raw_type = str(col["type"])  # SQLAlchemy type object to string
                cleaned_type = clean_data_type(raw_type)  # Remove COLLATE and other verbose clauses

                column_data = {
                    "column_name": col["name"],
                    "data_type": cleaned_type,
                    "is_nullable": col["nullable"]
                }
                columns.append(column_data)

            # Get primary key constraint
            pk_constraint = inspector.get_pk_constraint(table_name)
            primary_key = None
            if pk_constraint and "constrained_columns" in pk_constraint:
                pk_columns = pk_constraint["constrained_columns"]
                # Only set primary_key if it's a single-column PK
                if len(pk_columns) == 1:
                    primary_key = pk_columns[0]

            # Get foreign keys
            fk_constraints = inspector.get_foreign_keys(table_name)
            foreign_keys = []

            for fk in fk_constraints:
                # SQLAlchemy FK structure:
                # {
                #     'name': 'FK_...',
                #     'constrained_columns': ['ColumnInThisTable'],
                #     'referred_table': 'ReferencedTable',
                #     'referred_columns': ['ReferencedColumn']
                # }
                constrained_cols = fk.get("constrained_columns", [])
                referred_table = fk.get("referred_table")
                referred_cols = fk.get("referred_columns", [])

                # Handle multi-column FKs by creating separate entries
                for i, fk_col in enumerate(constrained_cols):
                    ref_col = referred_cols[i] if i < len(referred_cols) else None

                    foreign_key_data = {
                        "foreign_key": fk_col,
                        "primary_key_table": referred_table,
                        "primary_key_column": ref_col
                    }
                    foreign_keys.append(foreign_key_data)

            # Build table schema
            table_schema = {
                "table_name": table_name,
                "columns": columns
            }

            # Add metadata if we have a primary key
            if primary_key:
                table_schema["metadata"] = {
                    "primary_key": primary_key
                }

            # Add foreign keys if any exist
            if foreign_keys:
                table_schema["foreign_keys"] = foreign_keys

            schema.append(table_schema)

        logger.info(
            f"Schema introspection completed",
            extra={
                "table_count": len(schema),
                "total_columns": sum(len(t["columns"]) for t in schema),
                "total_foreign_keys": sum(len(t.get("foreign_keys", [])) for t in schema)
            }
        )

        return schema

    except Exception as e:
        logger.error(
            f"Failed to introspect schema using SQLAlchemy: {str(e)}",
            exc_info=True
        )
        raise Exception(f"Schema introspection failed: {e}")
    finally:
        # CRITICAL: Dispose of the SQLAlchemy engine to release connection pool resources
        # This prevents interference with the original pyodbc/sqlite3 connection
        if engine:
            engine.dispose()
            logger.debug("SQLAlchemy engine disposed")


def validate_schema_structure(schema: List[Dict[str, Any]]) -> bool:
    """
    Validate that the schema conforms to schema_model.py structure.

    Args:
        schema: List of table dictionaries

    Returns:
        True if valid, raises ValueError otherwise
    """
    for table in schema:
        # Required fields
        if "table_name" not in table:
            raise ValueError("Table missing 'table_name' field")

        if "columns" not in table or not isinstance(table["columns"], list):
            raise ValueError(f"Table {table['table_name']} missing or invalid 'columns'")

        # Validate columns
        for col in table["columns"]:
            required_col_fields = ["column_name", "data_type", "is_nullable"]
            for field in required_col_fields:
                if field not in col:
                    raise ValueError(
                        f"Column in {table['table_name']} missing '{field}' field"
                    )

        # Validate foreign keys if present
        if "foreign_keys" in table:
            for fk in table["foreign_keys"]:
                if "foreign_key" not in fk:
                    raise ValueError(
                        f"Foreign key in {table['table_name']} missing 'foreign_key' field"
                    )

    logger.info("Schema structure validation passed")
    return True
