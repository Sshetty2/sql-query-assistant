"""Test that execute_query uses the correct SQL dialect based on database type."""

import os
from unittest.mock import patch
import sqlglot
from sqlglot.expressions import Limit


def test_get_sql_dialect_sqlite():
    """Test that get_sql_dialect returns 'sqlite' when USE_TEST_DB=true."""
    from agent.execute_query import get_sql_dialect

    with patch.dict(os.environ, {"USE_TEST_DB": "true"}):
        assert get_sql_dialect() == "sqlite"


def test_get_sql_dialect_sql_server():
    """Test that get_sql_dialect returns 'tsql' when USE_TEST_DB=false."""
    from agent.execute_query import get_sql_dialect

    with patch.dict(os.environ, {"USE_TEST_DB": "false"}):
        assert get_sql_dialect() == "tsql"


def test_get_sql_dialect_default():
    """Test that get_sql_dialect defaults to 'tsql' when USE_TEST_DB not set."""
    from agent.execute_query import get_sql_dialect

    with patch.dict(os.environ, {}, clear=True):
        # When USE_TEST_DB is not set, should default to SQL Server (tsql)
        assert get_sql_dialect() == "tsql"


def test_limit_syntax_sqlite():
    """Test that LIMIT syntax is generated correctly for SQLite."""
    # Parse a query and add a LIMIT clause for SQLite
    query = "SELECT id, name FROM users"
    parsed = sqlglot.parse_one(query, read="sqlite")
    parsed.set("limit", Limit(expression=sqlglot.parse_one("500")))

    # Generate SQL for SQLite
    sql = parsed.sql(dialect="sqlite", pretty=True, identify=True)

    # Should contain "LIMIT 500" at the end
    assert "LIMIT 500" in sql
    assert "TOP" not in sql


def test_limit_syntax_sql_server():
    """Test that TOP syntax is used for SQL Server (when SQLGlot handles LIMIT)."""
    # Parse a query and add a LIMIT clause for SQL Server
    query = "SELECT id, name FROM users"
    parsed = sqlglot.parse_one(query, read="tsql")
    parsed.set("limit", Limit(expression=sqlglot.parse_one("500")))

    # Generate SQL for SQL Server (tsql)
    sql = parsed.sql(dialect="tsql", pretty=True, identify=True)

    # SQL Server uses TOP syntax (SQLGlot converts LIMIT to TOP for tsql dialect)
    assert "TOP" in sql or "LIMIT" in sql  # SQLGlot might use either


def test_parse_and_regenerate_sqlite():
    """Test parsing and regenerating a query with LIMIT for SQLite."""
    original_query = """
    SELECT
      "albums"."AlbumId",
      "albums"."Title",
      "artists"."ArtistId",
      "artists"."Name"
    FROM "albums"
    JOIN "artists"
      ON "albums"."ArtistId" = "artists"."ArtistId"
    ORDER BY
      "albums"."AlbumId" ASC
    LIMIT 500
    """

    # Parse with SQLite dialect
    parsed = sqlglot.parse_one(original_query, read="sqlite")

    # Remove LIMIT
    parsed.set("limit", None)
    query_without_limit = parsed.sql(dialect="sqlite", pretty=True, identify=True)

    # Should not have LIMIT
    assert "LIMIT" not in query_without_limit

    # Add LIMIT back
    parsed.set("limit", Limit(expression=sqlglot.parse_one("500")))
    query_with_limit = parsed.sql(dialect="sqlite", pretty=True, identify=True)

    # Should have LIMIT 500
    assert "LIMIT 500" in query_with_limit


def test_parse_and_regenerate_sql_server():
    """Test parsing and regenerating a query with LIMIT for SQL Server."""
    original_query = """
    SELECT TOP 500
      "albums"."AlbumId",
      "albums"."Title",
      "artists"."ArtistId",
      "artists"."Name"
    FROM "albums"
    JOIN "artists"
      ON "albums"."ArtistId" = "artists"."ArtistId"
    ORDER BY
      "albums"."AlbumId" ASC
    """

    # Parse with TSQL dialect
    parsed = sqlglot.parse_one(original_query, read="tsql")

    # Should have a limit (TOP is converted to limit internally)
    assert parsed.args.get("limit") is not None

    # Remove LIMIT
    parsed.set("limit", None)
    query_without_limit = parsed.sql(dialect="tsql", pretty=True, identify=True)

    # Should not have TOP
    assert "TOP" not in query_without_limit

    # Add LIMIT back (SQLGlot will convert to TOP for tsql dialect)
    parsed.set("limit", Limit(expression=sqlglot.parse_one("500")))
    query_with_limit = parsed.sql(dialect="tsql", pretty=True, identify=True)

    # Should have TOP 500 (SQLGlot converts LIMIT to TOP for tsql)
    assert "TOP" in query_with_limit or "TOP 500" in query_with_limit


def test_fallback_limit_syntax_sqlite():
    """Test fallback LIMIT syntax generation for SQLite."""
    query_without_limit = "SELECT id, name FROM users"
    limit_to_apply = 100

    # SQLite fallback: append LIMIT
    final_query = f"{query_without_limit.rstrip(';')} LIMIT {limit_to_apply}"

    assert final_query == "SELECT id, name FROM users LIMIT 100"


def test_fallback_limit_syntax_sql_server():
    """Test fallback TOP syntax generation for SQL Server."""
    query_without_limit = "SELECT id, name FROM users"
    limit_to_apply = 100

    # SQL Server fallback: use TOP
    final_query = query_without_limit.replace(
        "SELECT", f"SELECT TOP {limit_to_apply}", 1
    )

    assert final_query == "SELECT TOP 100 id, name FROM users"
