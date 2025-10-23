"""
Minimal PlannerOutput model for small LLMs (8GB models like qwen3:8b, llama3:8b).

This simplified model:
- Removes optional explanation fields (reason, comment, source_text)
- Removes advanced SQL features (window functions, subqueries, CTEs)
- Keeps only essential fields needed by the join synthesizer
- Reduces cognitive load on small models

Use this for PLANNER_COMPLEXITY=minimal
"""

from __future__ import annotations

from typing import List, Optional, Literal, Union
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator


# ---- Enums / literals -------------------------------------------------

ColumnRole = Literal["projection", "filter"]
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
DecisionMinimal = Literal["proceed", "clarify", "terminate"]  # Include clarify for ambiguities
AggregateFunc = Literal[
    "COUNT", "SUM", "AVG", "MIN", "MAX", "COUNT_DISTINCT"
]


# ---- Core structures --------------------------------------------------


class SelectedColumnMinimal(BaseModel):
    """Column selection - minimal version without explanation fields"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name from schema")
    column: str = Field(..., description="Exact column_name from schema")
    role: ColumnRole = Field(..., description="projection or filter")


ScalarOrNull = Union[str, int, float, bool, None]
ArrayValue = List[ScalarOrNull]


class FilterPredicateMinimal(BaseModel):
    """Filter condition - minimal version"""
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


class TableSelectionMinimal(BaseModel):
    """Table selection - minimal version"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Exact table_name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence (0-1)")
    include_only_for_join: bool = Field(
        False,
        description="True if table needed only for joins, not data projection",
    )
    columns: List[SelectedColumnMinimal] = Field(
        default_factory=list,
        description="Columns from this table (empty if include_only_for_join=True)",
    )
    filters: List[FilterPredicateMinimal] = Field(default_factory=list)


class JoinEdgeMinimal(BaseModel):
    """Join condition - minimal version"""
    model_config = ConfigDict(extra="forbid")

    from_table: str = Field(..., description="Left table in join")
    from_column: str = Field(..., description="Column on left table")
    to_table: str = Field(..., description="Right table in join")
    to_column: str = Field(..., description="Column on right table")
    join_type: Literal["inner", "left", "right", "full"] = Field("inner")
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class AggregateFunctionMinimal(BaseModel):
    """Aggregate function - minimal version"""
    model_config = ConfigDict(extra="forbid")

    function: AggregateFunc = Field(..., description="Aggregate function type")
    table: str = Field(..., description="Table containing the column")
    column: Optional[str] = Field(
        None,
        description="Column to aggregate (None for COUNT(*))",
    )
    alias: str = Field(..., description="Output column name")


class GroupByColumnMinimal(BaseModel):
    """GROUP BY column reference - minimal version"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Table name")
    column: str = Field(..., description="Column name")


class OrderByColumnMinimal(BaseModel):
    """ORDER BY column specification - minimal version"""
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., description="Table name")
    column: str = Field(..., description="Column name")
    direction: Literal["ASC", "DESC"] = Field("ASC", description="Sort direction")


class GroupBySpecMinimal(BaseModel):
    """GROUP BY specification - minimal version"""
    model_config = ConfigDict(extra="forbid")

    group_by_columns: List[GroupByColumnMinimal] = Field(
        ...,
        description="Columns to group by",
    )
    aggregates: List[AggregateFunctionMinimal] = Field(
        ..., description="Aggregate functions to compute"
    )
    having_filters: List[FilterPredicateMinimal] = Field(
        default_factory=list,
        description="HAVING clause filters (on aggregated results)",
    )


class PlannerOutputMinimal(BaseModel):
    """
    Minimal query plan for small LLMs - only essential fields.

    Includes:
    - Table selections with columns and filters
    - Join edges connecting tables
    - Basic aggregations (GROUP BY)
    - Decision and confidence

    Excludes:
    - Explanation fields (reason, comment, source_text)
    - Advanced features (window functions, CTEs, subqueries)
    - Clarify decision (only proceed/terminate)
    """

    model_config = ConfigDict(extra="forbid")

    decision: DecisionMinimal = Field(
        ...,
        description="'proceed' (when you have tables/joins) or 'terminate' (RARE - only when completely impossible)"
    )
    intent_summary: str = Field(
        ..., description="One sentence: what the user wants"
    )

    selections: Annotated[
        List[TableSelectionMinimal],
        Field(description="Tables to query. Must have at least 1 unless decision='terminate'.")
    ]
    global_filters: List[FilterPredicateMinimal] = Field(
        default_factory=list,
        description="Filters applying across tables",
    )
    join_edges: List[JoinEdgeMinimal] = Field(
        default_factory=list,
        description="Explicit joins: from_table.from_column = to_table.to_column",
    )

    # Basic aggregation support (most common advanced feature)
    group_by: Optional[GroupBySpecMinimal] = Field(
        None,
        description="Optional GROUP BY with aggregates and HAVING",
    )

    # Query ordering and limiting
    order_by: List[OrderByColumnMinimal] = Field(
        default_factory=list,
        description="ORDER BY specification. Use for 'last 10 logins' (ORDER BY LoginDate DESC LIMIT 10), 'top 5 customers', etc.",
    )
    limit: Optional[int] = Field(
        None,
        description="LIMIT/TOP number. Use for 'last 10 logins' (10), 'top 5 customers' (5), etc.",
    )

    ambiguities: List[str] = Field(
        default_factory=list, description="Assumptions or unclear points"
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
    def _dedup_tables(cls, v: List[TableSelectionMinimal]):
        """Remove duplicate tables"""
        seen = set()
        out: List[TableSelectionMinimal] = []
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
            # For 'proceed', require at least 1 selection
            if len(self.selections) == 0:
                raise ValueError(
                    "decision='proceed' requires at least 1 table in selections"
                )
        return self
