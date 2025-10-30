"""Pydantic model for LLM-based table selection in schema filtering."""

from pydantic import BaseModel, Field


class TableRelevance(BaseModel):
    """Model for a single table's relevance assessment."""

    table_name: str = Field(
        description="The name of the table being assessed"
    )
    is_relevant: bool = Field(
        description="Whether this table is relevant to answering the user's query"
    )
    reasoning: str = Field(
        description="Brief explanation of why this table is or isn't relevant"
    )
    relevant_columns: list[str] = Field(
        default_factory=list,
        description=(
            "List of column names from this table's 'Available columns' that are relevant to the query. "
            "IMPORTANT: You MUST only select columns from the exact list of 'Available columns' shown for this table. "
            "Do NOT invent or suggest column names that aren't in the available list. "
            "Include columns needed for: display, filtering, aggregation, sorting, or joins. "
            "Use the EXACT column names as shown (preserve casing and formatting). "
            "If the table has no available columns listed, return an empty list."
        )
    )


class TableSelectionOutput(BaseModel):
    """Model for LLM output when selecting relevant tables from vector search results."""

    selected_tables: list[TableRelevance] = Field(
        description=(
            "List of tables with relevance assessments. "
            "Only mark tables as relevant if they are directly needed to answer the query."
        )
    )
