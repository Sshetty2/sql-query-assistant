"""Router output model for conversational flow decisions."""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class RouterOutput(BaseModel):
    """
    Output from the conversational router that decides how to handle
    a follow-up query in the conversational flow.

    SECURITY NOTE: All SQL generation goes through the planner -> join synthesizer
    to prevent SQL injection. Router never generates SQL directly.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["update_plan", "rewrite_plan"] = Field(
        ...,
        description=(
            "Decision on how to proceed:\n"
            "- update_plan: For minor plan modifications (e.g., add filter, change grouping, "
            "add/remove columns), send to planner with update instructions\n"
            "- rewrite_plan: For major changes (e.g., different tables/domain, completely "
            "different question), send to planner for full replanning"
        ),
    )

    reasoning: str = Field(
        ...,
        description="Clear explanation of why this decision was made based on the user's request",
    )

    routing_instructions: str = Field(
        ...,
        description=(
            "Instructions for the planner on how to modify the plan. "
            "Should be specific and actionable (e.g., 'Add filter on Status column for active records only', "
            "'Add ProductName column to the selections', 'Change to query Customer table instead')."
        ),
    )
