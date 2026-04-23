// Package nodes holds the workflow graph node implementations. Each node is
// a small function with a stable signature so the Eino graph wiring (Phase 5)
// can compose them. For now the nodes are exposed for direct testing.
package nodes

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/models"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
	"github.com/sachit/sql-query-assistant/go-service/internal/vector"
)

// FilterSchemaInput collects only what the node actually reads — keeps unit
// tests trivial without dragging the full workflow State struct in.
type FilterSchemaInput struct {
	Schema       []schema.Table
	UserQuestion string
	TopK         int // defaults to TOP_MOST_RELEVANT_TABLES env or 10
}

// FilterSchemaOutput mirrors the two State fields the Python node produces:
// `filtered_schema` (full columns, used for downstream UI/modification options)
// and `truncated_schema` (LLM-pruned columns, used for planner context).
type FilterSchemaOutput struct {
	FilteredSchema  []schema.Table
	TruncatedSchema []schema.Table
	CandidateTables []string // post-vector + FK expansion, pre-LLM
	SelectedTables  []string // post-LLM
	Reasoning       []models.TableRelevance
}

// FilterSchema runs the multi-stage table-selection pipeline:
//
//  1. Vector search: embed each table's "page content" and the user question,
//     keep top-K by cosine similarity.
//  2. Foreign-key expansion: pull in any table reachable in 2 hops via
//     introspected FKs so the LLM can see junction tables.
//  3. LLM reasoning: ask the model which tables are actually relevant and
//     which columns to project. Returns truncated schema for the planner.
//
// Domain-specific guidance (mapping tables, custom FK files) is intentionally
// omitted — the Python service skips those when USE_TEST_DB=true, which is the
// only mode the Go service supports today.
func FilterSchema(ctx context.Context, in FilterSchemaInput) (*FilterSchemaOutput, error) {
	if len(in.Schema) == 0 {
		return nil, fmt.Errorf("empty schema")
	}
	topK := in.TopK
	if topK <= 0 {
		if v, err := strconv.Atoi(os.Getenv("TOP_MOST_RELEVANT_TABLES")); err == nil && v > 0 {
			topK = v
		} else {
			topK = 10
		}
	}

	// --------------------------------------------------------------------
	// Stage 1: Vector search
	// --------------------------------------------------------------------
	candidates, err := vectorSearchCandidates(ctx, in.Schema, in.UserQuestion, topK)
	if err != nil {
		return nil, fmt.Errorf("stage 1 vector search: %w", err)
	}

	// --------------------------------------------------------------------
	// Stage 2: Foreign-key expansion (2 levels deep, both forward and reverse)
	// --------------------------------------------------------------------
	expanded := expandWithForeignKeys(candidates, in.Schema, 2)

	// --------------------------------------------------------------------
	// Stage 3: LLM reasoning
	// --------------------------------------------------------------------
	full, truncated, assessments, err := llmFilterTables(ctx, expanded, in.Schema, in.UserQuestion)
	if err != nil {
		// Fall back to the FK-expanded set rather than failing — the planner
		// can still try with too many tables, which is better than no output.
		full = expanded
		truncated = expanded
		assessments = nil
	}

	candidateNames := tableNames(expanded)
	selectedNames := tableNames(full)
	return &FilterSchemaOutput{
		FilteredSchema:  full,
		TruncatedSchema: truncated,
		CandidateTables: candidateNames,
		SelectedTables:  selectedNames,
		Reasoning:       assessments,
	}, nil
}

// vectorSearchCandidates embeds each table's page content + the user's
// question and returns the top-K most similar tables.
func vectorSearchCandidates(ctx context.Context, all []schema.Table, query string, k int) ([]schema.Table, error) {
	embedder, err := llm.NewEmbedder("")
	if err != nil {
		return nil, err
	}

	texts := make([]string, len(all))
	for i, t := range all {
		texts[i] = pageContent(t)
	}

	// Embed table summaries in one call, then the query in a second call.
	tableVecs, err := embedder.Embed(ctx, texts)
	if err != nil {
		return nil, fmt.Errorf("embed tables: %w", err)
	}
	queryVecs, err := embedder.Embed(ctx, []string{query})
	if err != nil {
		return nil, fmt.Errorf("embed query: %w", err)
	}
	if len(queryVecs) == 0 {
		return nil, fmt.Errorf("embedder returned no vectors for query")
	}

	store := vector.NewStore[schema.Table]()
	for i, t := range all {
		store.Add(vector.Doc[schema.Table]{Text: texts[i], Metadata: t}, tableVecs[i])
	}

	results, err := store.Search(queryVecs[0], k)
	if err != nil {
		return nil, err
	}
	out := make([]schema.Table, len(results))
	for i, r := range results {
		out[i] = r.Doc.Metadata
	}
	return out, nil
}

// pageContent mirrors agent/filter_schema.py:get_page_content. Used as the
// text fed to the embedding model for each table.
func pageContent(t schema.Table) string {
	var b strings.Builder
	b.WriteString("Table: ")
	b.WriteString(t.TableName)
	if len(t.ForeignKeys) > 0 {
		refs := make([]string, 0, len(t.ForeignKeys))
		for _, fk := range t.ForeignKeys {
			refs = append(refs, fmt.Sprintf("%s -> %s", fk.ForeignKey, fk.PrimaryKeyTable))
		}
		b.WriteString(". Related to: ")
		b.WriteString(strings.Join(refs, ", "))
	}
	return b.String()
}

// expandWithForeignKeys recursively pulls in tables linked via FK references,
// both forward (`from_table → to_table`) and reverse (tables that reference us).
// max_depth=2 matches the Python default.
func expandWithForeignKeys(selected, all []schema.Table, maxDepth int) []schema.Table {
	allByName := make(map[string]schema.Table, len(all))
	for _, t := range all {
		allByName[strings.ToLower(t.TableName)] = t
	}
	selectedByName := make(map[string]schema.Table, len(selected))
	for _, t := range selected {
		selectedByName[strings.ToLower(t.TableName)] = t
	}

	// Build reverse FK lookup: pkTable -> tables that reference it.
	reverse := make(map[string][]string)
	for _, t := range all {
		for _, fk := range t.ForeignKeys {
			pk := strings.ToLower(fk.PrimaryKeyTable)
			reverse[pk] = append(reverse[pk], strings.ToLower(t.TableName))
		}
	}

	expanded := make(map[string]bool)
	for k := range selectedByName {
		expanded[k] = true
	}
	currentLevel := make(map[string]bool, len(selectedByName))
	for k := range selectedByName {
		currentLevel[k] = true
	}

	for depth := 1; depth <= maxDepth; depth++ {
		nextLevel := make(map[string]bool)
		for name := range currentLevel {
			t, ok := allByName[name]
			if !ok {
				continue
			}
			// Forward edges
			for _, fk := range t.ForeignKeys {
				ref := strings.ToLower(fk.PrimaryKeyTable)
				if !expanded[ref] {
					if _, exists := allByName[ref]; exists {
						expanded[ref] = true
						nextLevel[ref] = true
					}
				}
			}
			// Reverse edges
			for _, ref := range reverse[name] {
				if !expanded[ref] {
					expanded[ref] = true
					nextLevel[ref] = true
				}
			}
		}
		if len(nextLevel) == 0 {
			break
		}
		currentLevel = nextLevel
	}

	// Stable order: original selection order first, then alphabetical for new arrivals.
	out := make([]schema.Table, 0, len(expanded))
	seen := make(map[string]bool)
	for _, t := range selected {
		key := strings.ToLower(t.TableName)
		out = append(out, t)
		seen[key] = true
	}
	added := make([]string, 0)
	for k := range expanded {
		if !seen[k] {
			added = append(added, k)
		}
	}
	// Stable lexicographic order for predictable test output.
	for _, k := range sortedKeys(added) {
		out = append(out, allByName[k])
	}
	return out
}

func sortedKeys(s []string) []string {
	out := append([]string(nil), s...)
	// inline insertion sort — fewer than 30 elements expected
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && out[j-1] > out[j]; j-- {
			out[j-1], out[j] = out[j], out[j-1]
		}
	}
	return out
}

// llmFilterTables runs Stage 3: ask the configured filtering-stage model to
// pick relevant tables and columns from the FK-expanded candidates. Returns
// (full-column tables for the UI, truncated tables for the planner, raw
// per-table assessments).
func llmFilterTables(
	ctx context.Context,
	candidates []schema.Table,
	all []schema.Table,
	userQuery string,
) ([]schema.Table, []schema.Table, []models.TableRelevance, error) {
	client, err := llm.NewForStage(llm.StageFiltering)
	if err != nil {
		return nil, nil, nil, err
	}
	schemaJSON, err := models.TableSelectionOutputSchema()
	if err != nil {
		return nil, nil, nil, err
	}

	allByName := make(map[string]schema.Table, len(all))
	for _, t := range all {
		allByName[t.TableName] = t
	}

	var summaries strings.Builder
	for i, t := range candidates {
		full := allByName[t.TableName]
		fmt.Fprintf(&summaries, "### %d. **%s**\n", i+1, t.TableName)
		summaries.WriteString("Description: (not available)\n")
		cols := make([]string, 0, len(full.Columns))
		for _, c := range full.Columns {
			cols = append(cols, c.ColumnName)
		}
		if len(cols) > 0 {
			summaries.WriteString("Available columns: ")
			summaries.WriteString(strings.Join(cols, ", "))
			summaries.WriteByte('\n')
		}
		summaries.WriteByte('\n')
	}

	system := `# Schema Filtering Assistant

You help a SQL query assistant decide which tables and columns are relevant to a user question.

CRITICAL CONSTRAINT: You MUST only select columns from the exact "Available columns" list shown for each table.
Do NOT invent column names. Use the EXACT casing as shown.

Be liberal with table inclusion when joins might be needed, but only select columns that are actually
needed for: display, filtering, aggregation, sorting, or joins.`

	user := fmt.Sprintf(`## User's Question

%s

## Candidate Tables

%s

## Your Task

For each candidate table, return:
1. is_relevant: whether the table is needed
2. relevant_columns: exact column names from the Available columns list
3. reasoning: brief explanation`, userQuery, summaries.String())

	msgs := []llm.Message{
		{Role: llm.RoleSystem, Content: system},
		{Role: llm.RoleUser, Content: user},
	}

	var out models.TableSelectionOutput
	if err := client.StructuredOutput(ctx, msgs, schemaJSON, "TableSelectionOutput", &out); err != nil {
		return nil, nil, nil, err
	}

	relevant := make(map[string][]string)
	assessments := out.SelectedTables
	for _, a := range assessments {
		if a.IsRelevant {
			relevant[a.TableName] = a.RelevantColumns
		}
	}

	full := make([]schema.Table, 0, len(relevant))
	truncated := make([]schema.Table, 0, len(relevant))
	for name, cols := range relevant {
		t, ok := allByName[name]
		if !ok {
			continue // LLM hallucinated a table name
		}
		full = append(full, t)
		truncated = append(truncated, applyColumnFilter(t, cols))
	}
	return full, truncated, assessments, nil
}

// applyColumnFilter returns a copy of `t` keeping only columns whose name
// matches one of `keep` (case-insensitive, underscore-insensitive). If no
// columns match (LLM hallucinated names), keeps the full column list rather
// than emit an empty SELECT.
func applyColumnFilter(t schema.Table, keep []string) schema.Table {
	if len(keep) == 0 {
		return t
	}
	normalized := make(map[string]bool, len(keep))
	for _, k := range keep {
		normalized[normalize(k)] = true
	}
	out := t
	out.Columns = nil
	for _, c := range t.Columns {
		if normalized[normalize(c.ColumnName)] {
			out.Columns = append(out.Columns, c)
		}
	}
	if len(out.Columns) == 0 {
		// Fallback: LLM column names didn't match — keep them all rather than
		// produce a SELECT-nothing plan downstream.
		return t
	}
	return out
}

func normalize(s string) string {
	return strings.ToLower(strings.ReplaceAll(s, "_", ""))
}

func tableNames(ts []schema.Table) []string {
	out := make([]string, len(ts))
	for i, t := range ts {
		out[i] = t.TableName
	}
	return out
}
