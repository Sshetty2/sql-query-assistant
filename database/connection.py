import os
import pyodbc
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv

sample_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample-db.db')

print(sample_db_path)

def build_connection_string():
    """Build and return the connection string based on environment variables."""
    load_dotenv()
    
    # Check if we should use the test SQLite database
    if os.getenv('USE_TEST_DB', '').lower() == 'true':
        # For SQLite, we'll return just the path since we're using sqlite3 directly
        return sample_db_path
    
    # Default SQL Server connection string building
    connection_params = [
        "DRIVER={ODBC Driver 17 for SQL Server}",
        f"SERVER={os.getenv('DB_SERVER')}",
        f"DATABASE={os.getenv('DB_NAME')}",
    ]
    
    if os.getenv('DB_USER') and os.getenv('DB_PASSWORD'):
        connection_params.extend([
            f"UID={os.getenv('DB_USER')}",
            f"PWD={os.getenv('DB_PASSWORD')}"
        ])
    else:
        connection_params.append("Trusted_Connection=yes")
    
    return ";".join(connection_params)

def get_db_connection():
    """Get a SQLDatabase instance using the appropriate connection string."""
    if os.getenv('USE_TEST_DB', '').lower() == 'true':
        return SQLDatabase.from_uri(f"sqlite:///{sample_db_path}")
    
    connection_string = build_connection_string()
    return SQLDatabase.from_uri(f"mssql+pyodbc:///?odbc_connect={connection_string}")

def get_pyodbc_connection():
    """Get a raw database connection using the appropriate connection string."""
    connection_string = build_connection_string()
    if os.getenv('USE_TEST_DB', '').lower() == 'true':
        import sqlite3
        return sqlite3.connect(connection_string)
    return pyodbc.connect(connection_string)

def init_database():
    return get_db_connection()