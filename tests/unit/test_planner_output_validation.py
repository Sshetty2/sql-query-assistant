"""Unit tests for PlannerOutput validation logic."""

import pytest
from pydantic import ValidationError
from models.planner_output import PlannerOutput, TableSelection, SelectedColumn, JoinEdge


def test_terminate_with_selections_raises_error():
    """Test that terminate decision with selections raises validation error."""
    with pytest.raises(ValidationError, match="Invalid use of decision='terminate'"):
        PlannerOutput(
            decision="terminate",
            intent_summary="User wants to see applications",
            selections=[
                TableSelection(
                    table="tb_SoftwareTagsAndColors",
                    confidence=0.95,
                    columns=[
                        SelectedColumn(
                            table="tb_SoftwareTagsAndColors",
                            column="TagName",
                            role="projection",
                            value_type="string"
                        )
                    ]
                )
            ],
            join_edges=[],
            global_filters=[],
            termination_reason="Some reason"
        )


def test_terminate_with_joins_raises_error():
    """Test that terminate decision with joins raises validation error."""
    with pytest.raises(ValidationError, match="Invalid use of decision='terminate'"):
        PlannerOutput(
            decision="terminate",
            intent_summary="User wants to see applications",
            selections=[
                TableSelection(table="tb_Company", confidence=0.95),
                TableSelection(table="tb_Users", confidence=0.95)
            ],
            join_edges=[
                JoinEdge(
                    from_table="tb_Company",
                    from_column="ID",
                    to_table="tb_Users",
                    to_column="CompanyID"
                )
            ],
            termination_reason="Some reason"
        )


def test_terminate_without_termination_reason_raises_error():
    """Test that terminate decision requires termination_reason."""
    with pytest.raises(ValidationError, match="requires a termination_reason"):
        PlannerOutput(
            decision="terminate",
            intent_summary="Query is impossible",
            selections=[],
            join_edges=[],
            global_filters=[]
        )


def test_valid_terminate_no_plan_structure():
    """Test that terminate is valid when there's truly no plan structure."""
    plan = PlannerOutput(
        decision="terminate",
        intent_summary="User asked to order pizza in a security database",
        selections=[],
        join_edges=[],
        global_filters=[],
        termination_reason="This database contains security and IT asset data. There are no tables for food ordering."
    )
    assert plan.decision == "terminate"
    assert plan.termination_reason is not None


def test_proceed_with_selections_valid():
    """Test that proceed decision with selections is valid."""
    plan = PlannerOutput(
        decision="proceed",
        intent_summary="User wants to see applications",
        selections=[
            TableSelection(
                table="tb_SoftwareTagsAndColors",
                confidence=0.95,
                columns=[
                    SelectedColumn(
                        table="tb_SoftwareTagsAndColors",
                        column="TagName",
                        role="projection",
                        value_type="string"
                    )
                ]
            )
        ],
        join_edges=[],
        global_filters=[]
    )
    assert plan.decision == "proceed"


def test_clarify_with_selections_valid():
    """Test that clarify decision with selections is valid."""
    plan = PlannerOutput(
        decision="clarify",
        intent_summary="User wants to see applications but unclear which ones",
        selections=[
            TableSelection(
                table="tb_SoftwareTagsAndColors",
                confidence=0.95,
                columns=[
                    SelectedColumn(
                        table="tb_SoftwareTagsAndColors",
                        column="TagName",
                        role="projection",
                        value_type="string"
                    )
                ]
            )
        ],
        join_edges=[],
        global_filters=[],
        ambiguities=["Which type of applications - installed, licensed, or all?"]
    )
    assert plan.decision == "clarify"
