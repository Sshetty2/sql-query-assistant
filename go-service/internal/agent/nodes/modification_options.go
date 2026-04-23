package nodes

import (
	"regexp"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// FormatColumnNameForDisplay turns a database column name into a friendlier
// label for the UI. Mirrors agent/generate_modification_options.py:
//   - PascalCase     → "Pascal Case"
//   - snake_case     → "Snake Case"
//   - Acronyms (FK, PK, ID) stay uppercase when they appear as a snake-segment.
//   - Trailing acronyms (CompanyID → "Company ID") are split.
func FormatColumnNameForDisplay(name string) string {
	if name == "" {
		return name
	}
	if strings.Contains(name, "_") {
		var parts []string
		for _, p := range strings.Split(name, "_") {
			if p == "" {
				continue
			}
			if isAllUpper(p) {
				parts = append(parts, p)
			} else {
				parts = append(parts, titleCase(p))
			}
		}
		return strings.Join(parts, " ")
	}
	// PascalCase paths
	out := pascalLowerToUpper.ReplaceAllString(name, "$1 $2")
	out = trailingAcronym.ReplaceAllString(out, "$1 $2")
	out = consecutiveCaps.ReplaceAllString(out, "$1 $2")
	// If nothing was inserted (e.g. all-lowercase like "id"), title-case the start.
	if out == name && !hasUpper(out) {
		out = titleCase(out)
	}
	return out
}

func hasUpper(s string) bool {
	for _, r := range s {
		if r >= 'A' && r <= 'Z' {
			return true
		}
	}
	return false
}

var (
	// `(?<!^)(?=[A-Z][a-z])` in Python: insert a space before each capital
	// followed by a lowercase, except at the start. Go's `regexp` lacks
	// look-behind, so we instead scan and rebuild manually.
	pascalLowerToUpper = regexp.MustCompile(`([a-z0-9])([A-Z][a-z])`)
	trailingAcronym    = regexp.MustCompile(`([a-z])([A-Z]+)$`)
	consecutiveCaps    = regexp.MustCompile(`([A-Z]+)([A-Z][a-z])`)
)

func isAllUpper(s string) bool {
	for _, r := range s {
		if r < 'A' || r > 'Z' {
			return false
		}
	}
	return s != ""
}

func titleCase(s string) string {
	if s == "" {
		return s
	}
	first := s[0]
	if first >= 'a' && first <= 'z' {
		first -= 32
	}
	return string(first) + strings.ToLower(s[1:])
}

// GenerateModificationOptions builds the UI-facing options struct from the
// executed plan and the schema we used during this query. Pure function — no
// LLM, no IO.
//
// `executedPlan` is the plan actually run (so we know which columns are
// "selected" today). `filteredSchema` provides the full column list per
// table so the UI can offer add-column buttons for unselected ones.
func GenerateModificationOptions(executedPlan *models.PlannerOutput, filteredSchema []schema.Table) *models.ModificationOptions {
	if executedPlan == nil {
		return &models.ModificationOptions{
			Tables: map[string]models.TableOptions{},
		}
	}

	// table → column → role/reason from the plan
	selectedMap := make(map[string]map[string]string, len(executedPlan.Selections))
	for _, sel := range executedPlan.Selections {
		if _, ok := selectedMap[sel.Table]; !ok {
			selectedMap[sel.Table] = map[string]string{}
		}
		for _, c := range sel.Columns {
			selectedMap[sel.Table][c.Column] = string(c.Role)
		}
	}

	tables := make(map[string]models.TableOptions, len(executedPlan.Selections))
	var sortable []models.SortableColumn

	for _, sel := range executedPlan.Selections {
		schemaCols := lookupSchemaColumns(sel.Table, filteredSchema)
		columns := make([]models.ColumnOption, 0, len(schemaCols))

		for _, sc := range schemaCols {
			role, isSelected := selectedMap[sel.Table][sc.ColumnName]
			friendly := FormatColumnNameForDisplay(sc.ColumnName)
			columns = append(columns, models.ColumnOption{
				Name:         sc.ColumnName,
				DisplayName:  friendly,
				Type:         sc.DataType,
				Selected:     isSelected,
				Role:         role,
				IsPrimaryKey: false, // schema introspection doesn't currently surface PK per column
				IsNullable:   sc.IsNullable,
			})
			sortable = append(sortable, models.SortableColumn{
				Table:       sel.Table,
				Column:      sc.ColumnName,
				Type:        sc.DataType,
				DisplayName: sel.Table + "." + friendly,
			})
		}

		tables[sel.Table] = models.TableOptions{
			Alias:   sel.Alias,
			Columns: columns,
		}
	}

	out := &models.ModificationOptions{
		Tables:          tables,
		CurrentOrderBy:  cloneOrderBy(executedPlan.OrderBy),
		CurrentLimit:    executedPlan.Limit,
		SortableColumns: sortable,
	}
	return out
}

func lookupSchemaColumns(tableName string, sch []schema.Table) []schema.Column {
	for _, t := range sch {
		if strings.EqualFold(t.TableName, tableName) {
			return t.Columns
		}
	}
	return nil
}

// cloneOrderBy returns a defensive copy so callers can't mutate the plan
// through the modification options payload.
func cloneOrderBy(in []models.OrderByColumn) []models.OrderByColumn {
	if len(in) == 0 {
		return nil
	}
	out := make([]models.OrderByColumn, len(in))
	copy(out, in)
	return out
}
