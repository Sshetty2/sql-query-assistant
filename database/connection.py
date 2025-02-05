import os
from langchain_community.utilities import SQLDatabase
from dotenv import load_dotenv

def build_connection_string():
    """Build and return the SQL Server connection string based on environment variables."""
    load_dotenv()
    
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
    """Get a SQLDatabase instance using the connection string."""
    connection_string = build_connection_string()
    return SQLDatabase.from_uri(f"mssql+pyodbc:///?odbc_connect={connection_string}")

def get_pyodbc_connection():
    """Get a raw pyodbc connection using the connection string."""
    import pyodbc
    connection_string = build_connection_string()
    return pyodbc.connect(connection_string) 

def init_database():
    from database.connection import get_db_connection
    return get_db_connection()