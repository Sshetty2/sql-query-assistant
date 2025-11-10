"""Test that SQLite connections can be used across threads."""

import os
import threading
from database.connection import get_pyodbc_connection


def test_sqlite_connection_across_threads():
    """Test that SQLite connection created in one thread can be used in another."""
    # Set up test environment
    os.environ["USE_TEST_DB"] = "true"

    connection = None
    result = {"success": False, "error": None}

    def create_connection():
        """Create connection in thread 1."""
        nonlocal connection
        connection = get_pyodbc_connection()

    def use_connection():
        """Use connection in thread 2."""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            assert row[0] == 1
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)

    # Create connection in thread 1
    thread1 = threading.Thread(target=create_connection)
    thread1.start()
    thread1.join()

    # Use connection in thread 2
    thread2 = threading.Thread(target=use_connection)
    thread2.start()
    thread2.join()

    # Cleanup
    if connection:
        connection.close()

    # Verify success
    assert result["success"], f"Cross-thread usage failed: {result['error']}"


def test_sqlite_connection_cursor_in_different_thread():
    """Test that cursor operations work across threads."""
    # Set up test environment
    os.environ["USE_TEST_DB"] = "true"

    connection = get_pyodbc_connection()
    errors = []

    def run_query():
        """Run a query in a different thread."""
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM albums")
            result = cursor.fetchone()
            assert result is not None
        except Exception as e:
            errors.append(str(e))

    # Run query in different thread
    thread = threading.Thread(target=run_query)
    thread.start()
    thread.join()

    # Cleanup
    connection.close()

    # Verify no errors
    assert len(errors) == 0, f"Query execution failed: {errors}"


def test_sequential_thread_usage():
    """Test that connection can be used sequentially by different threads.

    This mimics the LangGraph workflow pattern where different nodes
    (potentially in different threads) use the connection sequentially.
    """
    # Set up test environment
    os.environ["USE_TEST_DB"] = "true"

    connection = get_pyodbc_connection()
    results = []
    errors = []

    def run_query(thread_id):
        """Run a query in a thread."""
        try:
            cursor = connection.cursor()
            cursor.execute(f"SELECT {thread_id} as value")
            result = cursor.fetchone()
            results.append((thread_id, result[0]))
        except Exception as e:
            errors.append((thread_id, str(e)))

    # Run queries sequentially in different threads (like LangGraph workflow)
    for i in range(5):
        thread = threading.Thread(target=run_query, args=(i,))
        thread.start()
        thread.join()  # Wait for each thread to complete before starting next

    # Cleanup
    connection.close()

    # Verify all threads succeeded
    assert len(errors) == 0, f"Some queries failed: {errors}"
    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    for thread_id, value in results:
        assert value == thread_id, f"Thread {thread_id} got unexpected value: {value}"
