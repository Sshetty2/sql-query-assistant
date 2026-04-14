"""SQL safety validation utilities.

Provides a reusable guard that rejects any non-SELECT SQL before it reaches
the database.  Used by both the main query execution pipeline and the
execute-sql endpoint.
"""

import sqlglot
import sqlglot.expressions as exp


def validate_select_only(sql: str) -> None:
    """Raise ValueError if *sql* contains anything other than SELECT statements.

    Uses the sqlglot parser to inspect every statement in the string.
    INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, etc. are all rejected.
    """
    try:
        statements = sqlglot.parse(sql)
        for stmt in statements:
            if stmt is None:
                continue
            if not isinstance(stmt, exp.Select):
                raise ValueError(
                    f"Only SELECT statements are allowed. "
                    f"Got: {type(stmt).__name__}"
                )
    except sqlglot.errors.ParseError:
        raise ValueError("Could not validate SQL statement")
