"""
Standard PlannerOutput model for medium-sized LLMs (13B-30B models like mixtral, qwen2.5:14b).

This balanced model:
- Keeps `reason` fields for debugging and explanation
- Supports all 3 decision types (proceed, clarify, terminate)
- Includes GROUP BY with aggregations and HAVING
- Removes rarest advanced features (window functions, CTEs, subqueries)
- Removes less useful fields (source_text, comment, candidate_keys)

Use this for PLANNER_COMPLEXITY=standard
"""

from __future__ import annotations

from typing import List, Optional, Literal, Union
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
    "starts_with",
    "ends_with",
    "is_null",
    "is_not_null",
]
Decision = Literal["proceed", "clarify", "terminate"]
AggregateFunc = Literal[
    "COUNT", "SUM", "AVG", "MIN", "MAX", "COUNT_DISTINCT"
]


# ---- Core structures --------------------------------------------------


class SelectedColumnStandard(BaseModel):
    """Column selection with optional reason field"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name from schema")
    column: str = Field(..., description="Exact column_name from schema")
    role: ColumnRole = Field(..., description="projection or filter")
    reason: Optional[str] = Field(
        None, description="Why this column was selected"
    )
    value_type: ValueType = Field(
        "unknown", description="Best-effort type hint"
    )


ScalarOrNull = Union[str, int, float, bool, None]
ArrayValue = List[ScalarOrNull]


class FilterPredicateStandard(BaseModel):
    """Filter condition"""
    model_config = ConfigDict(extra="forbid")

    table: str
    column: str
    op: Op
    value: Optional[Union[ScalarOrNull, ArrayValue]] = Field(
        None,
        description="Scalar, list for 'in'/'not_in', or [low, high] for 'between'",
    )

    @field_validator("value")
    @classmethod
    def _normalize_between(cls, v, info):
        if info.data.get("op") == "between":
            if not (isinstance(v, list) and len(v) == 2):
                raise ValueError("For 'between', value must be [low, high]")
        return v


class TableSelectionStandard(BaseModel):
    """Table selection with reason field"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name")
    alias: Optional[str] = Field(
        None, description="Optional short alias"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence (0-1)"
    )
    reason: Optional[str] = Field(None, description="Why this table was selected")
    include_only_for_join: bool = Field(
        False,
        description="True if table needed only for joins",
    )
    columns: List[SelectedColumnStandard] = Field(
        default_factory=list,
        description="Columns from this table",
    )
    filters: List[FilterPredicateStandard] = Field(default_factory=list)


class JoinEdgeStandard(BaseModel):
    """Join condition with reason field"""
    model_config = ConfigDict(extra="forbid")

    from_table: str = Field(..., description="Left table in join")
    from_column: str = Field(..., description="Column on left table")
    to_table: str = Field(..., description="Right table in join")
    to_column: str = Field(..., description="Column on right table")
    join_type: Literal["inner", "left", "right", "full"] = Field("inner")
    reason: Optional[str] = Field(None, description="Why this join is needed")
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class AggregateFunctionStandard(BaseModel):
    """Aggregate function"""
    model_config = ConfigDict(extra="forbid")

    function: AggregateFunc = Field(..., description="Aggregate function type")
    table: str = Field(..., description="Table containing the column")
    column: Optional[str] = Field(
        None,
        description="Column to aggregate (None for COUNT(*))",
    )
    alias: str = Field(..., description="Output column name")


class GroupByColumnStandard(BaseModel):
    """GROUP BY column reference"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Table name")
    column: str = Field(..., description="Column name")


class OrderByColumnStandard(BaseModel):
    """ORDER BY column specification"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Table name")
    column: str = Field(..., description="Column name")
    direction: Literal["ASC", "DESC"] = Field("ASC", description="Sort direction")


class GroupBySpecStandard(BaseModel):
    """GROUP BY specification"""
    model_config = ConfigDict(extra="forbid")

    group_by_columns: List[GroupByColumnStandard] = Field(
        ...,
        description="Columns to group by",
    )
    aggregates: List[AggregateFunctionStandard] = Field(
        ..., description="Aggregate functions to compute"
    )
    having_filters: List[FilterPredicateStandard] = Field(
        default_factory=list,
        description="HAVING clause filters",
    )


class PlannerOutputStandard(BaseModel):
    """
    Standard query plan for medium-sized LLMs (13B-30B models).

    Includes:
    - Table selections with columns, filters, and reasons
    - Join edges with explanations
    - Aggregations (GROUP BY)
    - All 3 decision types (proceed, clarify, terminate)

    Excludes:
    - Window functions (rare)
    - CTEs (rare)
    - Subqueries (rare)
    - Less useful fields (source_text, comment, candidate_keys)
    """

    model_config = ConfigDict(extra="forbid")

    decision: Decision = Field(
        ...,
        description="'proceed' (have a plan), 'clarify' (ambiguous), or 'terminate' (RARE - completely impossible)"
    )
    intent_summary: str = Field(
        ..., description="One sentence: what the user wants"
    )

    selections: Annotated[
        List[TableSelectionStandard],
        Field(description="Tables to query. Must have at least 1 unless decision='terminate'.")
    ]
    global_filters: List[FilterPredicateStandard] = Field(
        default_factory=list,
        description="Filters applying across tables",
    )
    join_edges: List[JoinEdgeStandard] = Field(
        default_factory=list,
        description="Explicit joins: from_table.from_column = to_table.to_column",
    )

    # Aggregation support
    group_by: Optional[GroupBySpecStandard] = Field(
        None,
        description="Optional GROUP BY with aggregates and HAVING",
    )

    # Query ordering and limiting
    order_by: List[OrderByColumnStandard] = Field(
        default_factory=list,
        description="ORDER BY specification. Use for 'last 10 logins' (ORDER BY LoginDate DESC), 'top 5 customers' (ORDER BY Revenue DESC), etc.",  # noqa: E501
    )
    limit: Optional[int] = Field(
        None,
        description="LIMIT/TOP number. Use for 'last 10 logins' (10), 'top 5 customers' (5), etc.",
    )

    ambiguities: List[str] = Field(
        default_factory=list, description="Assumptions or questions"
    )
    termination_reason: Optional[str] = Field(
        None, description="Why query terminated (only when decision='terminate')"
    )
    confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in plan (0.0 to 1.0)"
    )

    @field_validator("selections")
    @classmethod
    def _dedup_tables(cls, v: List[TableSelectionStandard]):
        """Remove duplicate tables"""
        seen = set()
        out: List[TableSelectionStandard] = []
        for t in v:
            key = t.table.lower()
            if key not in seen:
                out.append(t)
                seen.add(key)
        return out

    @model_validator(mode="after")
    def _validate_join_tables_present(self):
        """Ensure join_edges reference tables in selections"""
        selected = {s.table.lower(): s for s in self.selections}
        missing: List[str] = []
        for e in self.join_edges:
            if e.from_table.lower() not in selected:
                missing.append(e.from_table)
            if e.to_table.lower() not in selected:
                missing.append(e.to_table)
        if missing:
            raise ValueError(
                f"join_edges reference tables not in selections: {sorted(set(missing))}"
            )

        # Auto-mark tables without columns as join-only
        for s in self.selections:
            if not s.columns and not s.include_only_for_join:
                s.include_only_for_join = True

        return self

    @model_validator(mode="after")
    def _validate_terminate_decision(self):
        """
        Validate that 'terminate' is only used when no plan exists.
        If there are selections, joins, or filters, decision should be 'proceed'.
        """
        if self.decision == "terminate":
            has_plan_structure = (
                len(self.selections) > 0 or
                len(self.join_edges) > 0 or
                len(self.global_filters) > 0 or
                self.group_by is not None
            )
            if has_plan_structure:
                raise ValueError(
                    "Invalid use of decision='terminate': You created a plan with tables/joins/filters. "
                    "Use decision='proceed' instead. Only use 'terminate' when the query is completely "
                    "impossible and you have ZERO relevant tables."
                )
            if not self.termination_reason:
                raise ValueError(
                    "decision='terminate' requires a termination_reason explaining why"
                )
        else:
            # For 'proceed' and 'clarify', require at least 1 selection
            if len(self.selections) == 0:
                raise ValueError(
                    f"decision='{self.decision}' requires at least 1 table in selections"
                )
        return self
