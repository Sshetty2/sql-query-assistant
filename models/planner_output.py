from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ---- Enums / literals -------------------------------------------------

ColumnRole = Literal["projection", "filter", "group_by", "order_by"]
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
    role: ColumnRole = Field(..., description="How this column is intended to be used")
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
    # Values are intentionally flexible; downstream will validate & coerce types.
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
        op = info.data.get("op")
        if op == "between":
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError("For 'between', value must be [low, high]")
        return v


class TableSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name")
    alias: Optional[str] = Field(
        None, description="Optional short alias for downstream readability"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence the table is relevant (0–1)"
    )
    reason: Optional[str] = Field(None, description="Why this table was selected")
    # columns chosen from this table (subset of SelectedColumn with table fixed)
    columns: List[SelectedColumn] = Field(
        default_factory=list, description="Columns of interest from this table"
    )
    # filters scoped to this table only (global filters live separately if they span multiple tables)
    filters: List[FilterPredicate] = Field(default_factory=list)
    # Optional: surface key material present in the schema for the join planner to consider
    candidate_keys: Optional[Dict[str, List[str]]] = Field(
        None,
        description="Optional hints like {'primary_keys':['ID'], 'foreign_keys':['CompanyID','CVEID']}",
    )


class JoinHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Not a hard join plan—just an edge the next agent may consider.
    from_table: str
    to_table: str
    via: Optional[str] = Field(
        None,
        description="Name of FK column in from_table or recipe label if known (best effort)",
    )
    reason: Optional[str] = Field(None, description="Why this edge might be relevant")
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class TimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional resolved time windows (best effort). Downstream can convert to true date predicates.
    from_date: Optional[str] = Field(None, description="YYYY-MM-DD if inferred")
    to_date: Optional[str] = Field(None, description="YYYY-MM-DD if inferred")
    relative_phrase: Optional[str] = Field(
        None, description="Original NL like 'last 30 days'"
    )


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    intent_summary: str = Field(
        ..., description="One sentence summary of what the user wants"
    )

    # Use Annotated+Field(min_length=1) for v2-friendly min-length constraint
    selections: Annotated[List[TableSelection], Field(min_length=1)]

    global_filters: List[FilterPredicate] = Field(
        default_factory=list,
        description="Filters that logically apply across tables (e.g., vendor='Cisco')",
    )
    group_by: List[SelectedColumn] = Field(
        default_factory=list, description="Columns intended for grouping"
    )
    order_by: List[SelectedColumn] = Field(
        default_factory=list, description="Columns intended for ordering"
    )
    time_context: Optional[TimeContext] = None
    join_hints: List[JoinHint] = Field(
        default_factory=list, description="Optional edges; not a join plan"
    )
    ambiguities: List[str] = Field(
        default_factory=list,
        description="Questions the next step or user should resolve",
    )
    notes_for_join_planner: Optional[str] = Field(
        None,
        description="Freeform guidance to the join/SQL agent (e.g., expected grain, dedup strategy hints)",
    )
    confidence: float = Field(0.7, ge=0.0, le=1.0)

    @field_validator("selections")
    @classmethod
    def _tables_dedup(cls, v: List[TableSelection]):
        seen = set()
        out: List[TableSelection] = []
        for t in v:
            key = t.table.lower()
            if key not in seen:
                out.append(t)
                seen.add(key)
        return out
