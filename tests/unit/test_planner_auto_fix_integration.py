"""Integration test for planner auto-fix with Pydantic validation."""

import pytest
from pydantic import ValidationError
from models.planner_output_minimal import PlannerOutputMinimal
from agent.planner import auto_fix_join_edges


def test_auto_fix_prevents_validation_error():
    """
    Test that auto_fix_join_edges fixes data that would fail Pydantic validation.

    This simulates the real-world scenario where an LLM generates a plan with
    join_edges referencing tables not in selections, which violates the Pydantic
    validation rule.
    """
    # Create a plan that would fail Pydantic validation
    # (join_edges references tb_Company which is not in selections)
    invalid_plan = {
        "decision": "proceed",
        "intent_summary": "List users with company information",
        "confidence": 0.8,
        "selections": [
            {
                "table": "tb_Users",
                "confidence": 0.9,
                "columns": [
                    {"table": "tb_Users", "column": "Email", "role": "projection"}
                ],
                "filters": [],
            }
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

    # Verify that this would fail Pydantic validation
    with pytest.raises(ValidationError) as exc_info:
        PlannerOutputMinimal(**invalid_plan)

    # Check that error message mentions the missing table
    assert "join_edges reference tables not" in str(exc_info.value)

    # Apply auto-fix
    fixed_plan = auto_fix_join_edges(invalid_plan)

    # Now it should pass Pydantic validation
    planner_output = PlannerOutputMinimal(**fixed_plan)

    # Verify the result
    assert planner_output.decision == "proceed"
    assert len(planner_output.selections) == 2
    assert {sel.table for sel in planner_output.selections} == {"tb_Users", "tb_Company"}

    # Verify the auto-added table has correct properties
    company_selection = next(
        sel for sel in planner_output.selections if sel.table == "tb_Company"
    )
    assert company_selection.confidence == 0.7
    assert company_selection.include_only_for_join is True


def test_auto_fix_with_multiple_missing_tables():
    """Test auto-fix with multiple missing tables in join_edges."""
    invalid_plan = {
        "decision": "proceed",
        "intent_summary": "List computers with company and CVE information",
        "confidence": 0.8,
        "selections": [
            {
                "table": "tb_SaasComputers",
                "confidence": 0.9,
                "columns": [
                    {
                        "table": "tb_SaasComputers",
                        "column": "Name",
                        "role": "projection",
                    }
                ],
                "filters": [],
            }
        ],
        "join_edges": [
            {
                "from_table": "tb_SaasComputers",
                "from_column": "CompanyID",
                "to_table": "tb_Company",
                "to_column": "ID",
            },
            {
                "from_table": "tb_SaasComputers",
                "from_column": "ID",
                "to_table": "tb_SaasComputerCVEMap",
                "to_column": "ComputerID",
            },
        ],
    }

    # This should fail validation (2 missing tables)
    with pytest.raises(ValidationError):
        PlannerOutputMinimal(**invalid_plan)

    # Apply auto-fix
    fixed_plan = auto_fix_join_edges(invalid_plan)

    # Should now pass validation
    planner_output = PlannerOutputMinimal(**fixed_plan)

    # Verify all 3 tables are present
    assert len(planner_output.selections) == 3
    assert {sel.table for sel in planner_output.selections} == {
        "tb_SaasComputers",
        "tb_Company",
        "tb_SaasComputerCVEMap",
    }


def test_auto_fix_preserves_valid_plans():
    """Test that auto-fix doesn't modify already-valid plans."""
    valid_plan = {
        "decision": "proceed",
        "intent_summary": "List users with their companies",
        "confidence": 0.9,
        "selections": [
            {
                "table": "tb_Users",
                "confidence": 0.9,
                "columns": [
                    {"table": "tb_Users", "column": "Email", "role": "projection"}
                ],
                "filters": [],
            },
            {
                "table": "tb_Company",
                "confidence": 0.9,
                "columns": [
                    {"table": "tb_Company", "column": "Name", "role": "projection"}
                ],
                "filters": [],
            },
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

    # This should pass validation already
    planner_output_before = PlannerOutputMinimal(**valid_plan)

    # Apply auto-fix
    fixed_plan = auto_fix_join_edges(valid_plan)

    # Should still pass validation and have same number of selections
    planner_output_after = PlannerOutputMinimal(**fixed_plan)

    assert len(planner_output_after.selections) == len(planner_output_before.selections)
    assert {sel.table for sel in planner_output_after.selections} == {
        "tb_Users",
        "tb_Company",
    }
