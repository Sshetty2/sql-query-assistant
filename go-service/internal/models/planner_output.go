// Package models mirrors the Pydantic schemas in ../../models/planner_output.py.
// JSON tags use snake_case to match the Python service so plans are interchangeable.
package models

// ColumnRole is "projection" or "filter".
type ColumnRole string

// FilterOp matches the Op literal in planner_output.py.
type FilterOp string

const (
	OpEq         FilterOp = "="
	OpNeq        FilterOp = "!="
	OpGt         FilterOp = ">"
	OpGte        FilterOp = ">="
	OpLt         FilterOp = "<"
	OpLte        FilterOp = "<="
	OpBetween    FilterOp = "between"
	OpIn         FilterOp = "in"
	OpNotIn      FilterOp = "not_in"
	OpLike       FilterOp = "like"
	OpILike      FilterOp = "ilike"
	OpStartsWith FilterOp = "starts_with"
	OpEndsWith   FilterOp = "ends_with"
	OpIsNull     FilterOp = "is_null"
	OpIsNotNull  FilterOp = "is_not_null"
	OpExists     FilterOp = "exists"
)

type Decision string

const (
	DecisionProceed   Decision = "proceed"
	DecisionClarify   Decision = "clarify"
	DecisionTerminate Decision = "terminate"
)

type AggregateFunc string

const (
	AggCount         AggregateFunc = "COUNT"
	AggSum           AggregateFunc = "SUM"
	AggAvg           AggregateFunc = "AVG"
	AggMin           AggregateFunc = "MIN"
	AggMax           AggregateFunc = "MAX"
	AggCountDistinct AggregateFunc = "COUNT_DISTINCT"
)

type WindowFunc string

const (
	WinRowNumber WindowFunc = "ROW_NUMBER"
	WinRank      WindowFunc = "RANK"
	WinDenseRank WindowFunc = "DENSE_RANK"
	WinNTile     WindowFunc = "NTILE"
	WinLag       WindowFunc = "LAG"
	WinLead      WindowFunc = "LEAD"
	WinSum       WindowFunc = "SUM"
	WinAvg       WindowFunc = "AVG"
	WinCount     WindowFunc = "COUNT"
	WinMin       WindowFunc = "MIN"
	WinMax       WindowFunc = "MAX"
)

type SortDirection string

const (
	SortAsc  SortDirection = "ASC"
	SortDesc SortDirection = "DESC"
)

type JoinType string

const (
	JoinInner JoinType = "inner"
	JoinLeft  JoinType = "left"
	JoinRight JoinType = "right"
	JoinFull  JoinType = "full"
)

type SelectedColumn struct {
	Table     string     `json:"table"`
	Column    string     `json:"column"`
	Role      ColumnRole `json:"role"`
	Reason    string     `json:"reason,omitempty"`
	ValueType string     `json:"value_type,omitempty"`
}

// FilterPredicate.Value uses `any` because it can be a scalar, list, or [low, high].
// The emitter inspects the runtime type; planner-output round-tripping preserves shape.
type FilterPredicate struct {
	Table      string   `json:"table"`
	Column     string   `json:"column"`
	Op         FilterOp `json:"op"`
	Value      any      `json:"value,omitempty"`
	SourceText string   `json:"source_text,omitempty"`
	Comment    string   `json:"comment,omitempty"`
}

type TableSelection struct {
	Table               string              `json:"table"`
	Alias               string              `json:"alias,omitempty"`
	Confidence          float64             `json:"confidence"`
	Reason              string              `json:"reason,omitempty"`
	IncludeOnlyForJoin  bool                `json:"include_only_for_join"`
	Columns             []SelectedColumn    `json:"columns"`
	Filters             []FilterPredicate   `json:"filters"`
	CandidateKeys       map[string][]string `json:"candidate_keys,omitempty"`
}

type JoinEdge struct {
	FromTable  string   `json:"from_table"`
	FromColumn string   `json:"from_column"`
	ToTable    string   `json:"to_table"`
	ToColumn   string   `json:"to_column"`
	JoinType   JoinType `json:"join_type"`
	Reason     string   `json:"reason,omitempty"`
	Confidence float64  `json:"confidence"`
}

type AggregateFunction struct {
	Function AggregateFunc `json:"function"`
	Table    string        `json:"table"`
	Column   string        `json:"column,omitempty"`
	Alias    string        `json:"alias"`
	Comment  string        `json:"comment,omitempty"`
}

type OrderByColumn struct {
	Table     string        `json:"table"`
	Column    string        `json:"column"`
	Direction SortDirection `json:"direction"`
}

type GroupBySpec struct {
	GroupByColumns []SelectedColumn    `json:"group_by_columns"`
	Aggregates     []AggregateFunction `json:"aggregates"`
	HavingFilters  []FilterPredicate   `json:"having_filters"`
}

type WindowFunction struct {
	Function    WindowFunc       `json:"function"`
	PartitionBy []SelectedColumn `json:"partition_by"`
	OrderBy     []OrderByColumn  `json:"order_by"`
	Alias       string           `json:"alias"`
	Comment     string           `json:"comment,omitempty"`
}

type SubqueryFilter struct {
	OuterTable      string            `json:"outer_table"`
	OuterColumn     string            `json:"outer_column"`
	Op              string            `json:"op"` // "in", "not_in", "exists", "not_exists"
	SubqueryTable   string            `json:"subquery_table"`
	SubqueryColumn  string            `json:"subquery_column"`
	SubqueryFilters []FilterPredicate `json:"subquery_filters"`
	Comment         string            `json:"comment,omitempty"`
}

type CTE struct {
	Name       string            `json:"name"`
	Selections []TableSelection  `json:"selections"`
	JoinEdges  []JoinEdge        `json:"join_edges"`
	Filters    []FilterPredicate `json:"filters"`
	GroupBy    *GroupBySpec      `json:"group_by,omitempty"`
}

type PlannerOutput struct {
	Decision          Decision          `json:"decision"`
	IntentSummary     string            `json:"intent_summary"`
	Selections        []TableSelection  `json:"selections"`
	GlobalFilters     []FilterPredicate `json:"global_filters"`
	JoinEdges         []JoinEdge        `json:"join_edges"`
	GroupBy           *GroupBySpec      `json:"group_by,omitempty"`
	WindowFunctions   []WindowFunction  `json:"window_functions"`
	SubqueryFilters   []SubqueryFilter  `json:"subquery_filters"`
	CTEs              []CTE             `json:"ctes"`
	OrderBy           []OrderByColumn   `json:"order_by"`
	Limit             *int              `json:"limit,omitempty"`
	Ambiguities       []string          `json:"ambiguities"`
	TerminationReason string            `json:"termination_reason,omitempty"`
	Confidence        float64           `json:"confidence"`
}
