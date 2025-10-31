"""Unit tests for planner auto-fix functionality."""

import pytest
from agent.planner import auto_fix_join_edges


def test_auto_fix_join_edges_adds_missing_tables():
    """Test that auto_fix_join_edges adds tables referenced in join_edges to selections."""
    plan = {
        "selections": [
            {"table": "tb_Users", "confidence": 0.9, "columns": [], "filters": []}
        ],
        "join_edges": [
            {
                "from_table": "tb_Users",
                "from_column": "CompanyID",
                "to_table": "tb_Company",  # tb_Company NOT in selections
                "to_column": "ID",
            }
        ],
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Check that tb_Company was added to selections
    tables_in_selections = {sel["table"] for sel in fixed_plan["selections"]}
    assert "tb_Users" in tables_in_selections
    assert "tb_Company" in tables_in_selections

    # Check that the added table has correct properties
    company_selection = next(
        sel for sel in fixed_plan["selections"] if sel["table"] == "tb_Company"
    )
    assert company_selection["confidence"] == 0.7  # Lower confidence for auto-added
    assert company_selection["include_only_for_join"] is True
    assert company_selection["columns"] == []
    assert company_selection["filters"] == []


def test_auto_fix_join_edges_multiple_missing_tables():
    """Test auto-fix with multiple missing tables."""
    plan = {
        "selections": [
            {"table": "tb_Applications", "confidence": 0.9, "columns": [], "filters": []}
        ],
        "join_edges": [
            {
                "from_table": "tb_Applications",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
            },
            {
                "from_table": "tb_Applications",
                "from_column": "UserID",
                "to_table": "tb_Users",
                "to_column": "ID",
            },
        ],
    }

    fixed_plan = auto_fix_join_edges(plan)

    tables_in_selections = {sel["table"] for sel in fixed_plan["selections"]}
    assert "tb_Applications" in tables_in_selections
    assert "tb_Company" in tables_in_selections
    assert "tb_Users" in tables_in_selections
    assert len(fixed_plan["selections"]) == 3


def test_auto_fix_join_edges_no_changes_needed():
    """Test that auto-fix doesn't modify plan when all tables are already in selections."""
    plan = {
        "selections": [
            {"table": "tb_Users", "confidence": 0.9, "columns": [], "filters": []},
            {"table": "tb_Company", "confidence": 0.9, "columns": [], "filters": []},
        ],
        "join_edges": [
            {
                "from_table": "tb_Users",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
            }
        ],
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Should have same number of selections
    assert len(fixed_plan["selections"]) == 2
    tables_in_selections = {sel["table"] for sel in fixed_plan["selections"]}
    assert tables_in_selections == {"tb_Users", "tb_Company"}


def test_auto_fix_join_edges_empty_join_edges():
    """Test auto-fix with no join_edges."""
    plan = {
        "selections": [
            {"table": "tb_Users", "confidence": 0.9, "columns": [], "filters": []}
        ],
        "join_edges": [],
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Should not modify selections
    assert len(fixed_plan["selections"]) == 1
    assert fixed_plan["selections"][0]["table"] == "tb_Users"


def test_auto_fix_join_edges_missing_join_edges_field():
    """Test auto-fix when join_edges field doesn't exist."""
    plan = {
        "selections": [
            {"table": "tb_Users", "confidence": 0.9, "columns": [], "filters": []}
        ]
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Should not modify selections
    assert len(fixed_plan["selections"]) == 1
    assert fixed_plan["selections"][0]["table"] == "tb_Users"


def test_auto_fix_join_edges_preserves_existing_selections():
    """Test that auto-fix preserves all properties of existing selections."""
    plan = {
        "selections": [
            {
                "table": "tb_Users",
                "confidence": 0.95,
                "columns": [
                    {"table": "tb_Users", "column": "Email", "role": "projection"}
                ],
                "filters": [
                    {"table": "tb_Users", "column": "IsActive", "op": "=", "value": True}
                ],
            }
        ],
        "join_edges": [
            {
                "from_table": "tb_Users",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
            }
        ],
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Check that original selection was preserved
    users_selection = next(
        sel for sel in fixed_plan["selections"] if sel["table"] == "tb_Users"
    )
    assert users_selection["confidence"] == 0.95
    assert len(users_selection["columns"]) == 1
    assert users_selection["columns"][0]["column"] == "Email"
    assert len(users_selection["filters"]) == 1
    assert users_selection["filters"][0]["column"] == "IsActive"

    # Check that new selection was added
    assert len(fixed_plan["selections"]) == 2
    company_selection = next(
        sel for sel in fixed_plan["selections"] if sel["table"] == "tb_Company"
    )
    assert company_selection["table"] == "tb_Company"


def test_auto_fix_join_edges_bidirectional_joins():
    """Test auto-fix handles bidirectional joins correctly."""
    plan = {
        "selections": [
            {"table": "tb_Users", "confidence": 0.9, "columns": [], "filters": []}
        ],
        "join_edges": [
            {
                "from_table": "tb_Users",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
            },
            {
                "from_table": "tb_Company",
                "from_column": "ID",
                "to_table": "tb_Users",
                "to_column": "CompanyID",
            },
        ],
    }

    fixed_plan = auto_fix_join_edges(plan)

    # Should add tb_Company once (not twice)
    tables_in_selections = {sel["table"] for sel in fixed_plan["selections"]}
    assert tables_in_selections == {"tb_Users", "tb_Company"}
    assert len(fixed_plan["selections"]) == 2
