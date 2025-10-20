"""Router output model for conversational flow decisions."""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class RouterOutput(BaseModel):
    """
    Output from the conversational router that decides how to handle
    a follow-up query in the conversational flow.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["revise_query_inline", "update_plan", "rewrite_plan"] = Field(
        ...,
        description=(
            "Decision on how to proceed:\n"
            "- revise_query_inline: For small SQL changes (e.g., add/remove a column), "
            "router generates the revised SQL directly\n"
            "- update_plan: For minor plan modifications (e.g., add filter, change grouping), "
            "send to planner with update instructions\n"
            "- rewrite_plan: For major changes (e.g., different tables/domain), "
            "send to planner for full replanning"
        ),
    )

    reasoning: str = Field(
        ...,
        description="Clear explanation of why this decision was made based on the user's request",
    )

    revised_query: Optional[str] = Field(
        None,
        description=(
            "Complete revised SQL query. Only populated when decision='revise_query_inline'. "
            "Should be executable SQL with all changes applied."
        ),
    )

    routing_instructions: Optional[str] = Field(
        None,
        description=(
            "Instructions for the planner on how to modify the plan. "
            "Only populated when decision='update_plan' or 'rewrite_plan'. "
            "Should be specific and actionable (e.g., 'Add filter on Status column for active records only')."
        ),
    )
