from __future__ import annotations

from typing import List, Optional, Literal, Dict, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator

# ---- Enums / literals -------------------------------------------------

ColumnRole = Literal["projection", "filter"]
ValueType = Literal[
    "string", "number", "integer", "boolean", "date", "datetime", "unknown"
]
Op = Literal[
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "between",
    "in",
    "not_in",
    "like",
    "ilike",
    "starts_with",
    "ends_with",
    "is_null",
    "is_not_null",
    "exists",
]
Decision = Literal["proceed", "clarify"]

# ---- Core structures --------------------------------------------------


class SelectedColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name from the provided schema")
    column: str = Field(..., description="Exact column_name from the provided schema")
    role: ColumnRole = Field(..., description="projection or filter")
    reason: Optional[str] = Field(
        None, description="Short rationale for choosing this column"
    )
    value_type: ValueType = Field(
        "unknown", description="Best-effort type for downstream validation"
    )


ScalarOrNull = Union[str, int, float, bool, None]
ArrayValue = List[ScalarOrNull]


class FilterPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    column: str
    op: Op
    value: Optional[Union[ScalarOrNull, ArrayValue]] = Field(
        None,
        description="Scalar, list for 'in'/'not_in', or [low, high] for 'between'. Null allowed for is_null ops.",
    )
    source_text: Optional[str] = Field(
        None, description="Snippet from the user query that triggered this filter"
    )
    comment: Optional[str] = Field(None, description="Why this filter was inferred")

    @field_validator("value")
    @classmethod
    def _normalize_between(cls, v, info):
        if info.data.get("op") == "between":
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError("For 'between', value must be [low, high]")
        return v


class TableSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name")
    alias: Optional[str] = Field(
        None, description="Optional short alias for readability"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence the table is relevant (0–1)"
    )
    reason: Optional[str] = Field(None, description="Why this table was selected")
    include_only_for_join: bool = Field(
        False,
        description="True if table is needed only to satisfy joins (no projection required)",
    )
    columns: List[SelectedColumn] = Field(
        default_factory=list,
        description="Columns of interest from this table (may be empty if include_only_for_join=True)",
    )
    filters: List[FilterPredicate] = Field(default_factory=list)
    candidate_keys: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Optional hints like {'primary_keys':['ID'], 'foreign_keys':['CompanyID','CVEID']}",
    )


class JoinEdge(BaseModel):
    """
    A concrete, machine-usable join edge. Not a vague hint.
    """

    model_config = ConfigDict(extra="forbid")

    from_table: str = Field(..., description="Left table in the join condition")
    from_column: str = Field(
        ..., description="Column on the left table (FK or join key)"
    )
    to_table: str = Field(..., description="Right table in the join condition")
    to_column: str = Field(
        ..., description="Column on the right table (PK or join key)"
    )
    join_type: Literal["inner", "left", "right", "full"] = Field(
        "inner",
        description="Preferred join type (planner suggestion; downstream may override)",
    )
    reason: Optional[str] = Field(None, description="Why this relationship is required")
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class PlannerOutput(BaseModel):
    """
    Minimal, actionable plan for the next agent:
    - Which tables are involved (and which are join-only)
    - Which columns to project/filter
    - Concrete join edges with columns
    - Optional global filters
    """

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    intent_summary: str = Field(
        ..., description="One sentence summary of what the user wants"
    )

    selections: Annotated[List[TableSelection], Field(min_length=1)]
    global_filters: List[FilterPredicate] = Field(
        default_factory=list,
        description="Filters that logically apply across tables (e.g., vendor='Cisco')",
    )
    join_edges: List[JoinEdge] = Field(
        default_factory=list,
        description="Explicit join edges: from_table.from_column = to_table.to_column",
    )
    ambiguities: List[str] = Field(
        default_factory=list, description="Questions to resolve or assumptions made"
    )
    confidence: float = Field(0.7, ge=0.0, le=1.0)

    @field_validator("selections")
    @classmethod
    def _dedup_tables(cls, v: List[TableSelection]):
        seen = set()
        out: List[TableSelection] = []
        for t in v:
            key = t.table.lower()
            if key not in seen:
                out.append(t)
                seen.add(key)
        return out

    @model_validator(mode="after")
    def _validate_join_tables_present(self):
        """
        Ensure every table referenced by join_edges is present in selections.
        Also ensure a table with no projected columns is marked include_only_for_join=True.
        """
        selected = {s.table.lower(): s for s in self.selections}
        missing: List[str] = []
        for e in self.join_edges:
            if e.from_table.lower() not in selected:
                missing.append(e.from_table)
            if e.to_table.lower() not in selected:
                missing.append(e.to_table)
        if missing:
            raise ValueError(
                f"join_edges reference tables not present in selections: {sorted(set(missing))}"
            )

        # Soft warning semantics implemented as normalization; you can switch to raising if desired.
        for s in self.selections:
            if not s.columns and not s.include_only_for_join:
                # If no columns provided, mark as join-only to be explicit.
                s.include_only_for_join = True
        return self
