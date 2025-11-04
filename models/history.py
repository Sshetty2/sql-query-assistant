"""Pydantic models for error correction and refinement history tracking."""

from pydantic import BaseModel, Field
from typing import Any


class ErrorCorrectionHistory(BaseModel):
    """Complete history record for an error correction attempt."""

    strategy: str = Field(
        description="The revised text-based strategy that was used to generate the corrected plan"
    )
    plan: dict[str, Any] = Field(
        description="The corrected PlannerOutput as JSON dict"
    )
    query: str = Field(
        description="The SQL query that failed with an error"
    )
    reasoning: str = Field(
        description="Explanation of what caused the error and how the plan was corrected"
    )
    error: str = Field(
        description="The original SQL error message that triggered the correction"
    )
    iteration: int = Field(
        description="Which error correction attempt this was (1, 2, 3, etc.)",
        ge=1
    )


class RefinementHistory(BaseModel):
    """Complete history record for a query refinement attempt."""

    strategy: str = Field(
        description="The refined text-based strategy that was used to generate the refined plan"
    )
    plan: dict[str, Any] = Field(
        description="The refined PlannerOutput as JSON dict"
    )
    query: str = Field(
        description="The SQL query that returned 0 results"
    )
    reasoning: str = Field(
        description="Explanation of why no results were returned and how to broaden the query"
    )
    iteration: int = Field(
        description="Which refinement attempt this was (1, 2, 3, etc.)",
        ge=1
    )
