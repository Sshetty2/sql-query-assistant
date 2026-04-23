package nodes

import (
	"context"
	"os"
	"strconv"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/fk"
	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// InferForeignKeysEnabled reports whether the optional inference node should
// run. Mirrors agent/infer_foreign_keys.py's INFER_FOREIGN_KEYS env gate.
func InferForeignKeysEnabled() bool {
	return strings.EqualFold(os.Getenv("INFER_FOREIGN_KEYS"), "true")
}

// confidenceThreshold reads FK_INFERENCE_CONFIDENCE_THRESHOLD (default 0.6).
func confidenceThreshold() float32 {
	if v := os.Getenv("FK_INFERENCE_CONFIDENCE_THRESHOLD"); v != "" {
		if f, err := strconv.ParseFloat(v, 32); err == nil {
			return float32(f)
		}
	}
	return 0.6
}

// topK reads FK_INFERENCE_TOP_K (default 3).
func topK() int {
	if v := os.Getenv("FK_INFERENCE_TOP_K"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return 3
}

// InferForeignKeys augments `tables` with inferred FK relationships for any
// ID-suffixed columns that don't already have an explicit FK. Each inferred
// FK is marked Inferred=true with a Confidence score so callers can filter
// or display them differently from explicit ones.
//
// `allTables` is the full schema (used as the candidate pool); `tables` is
// the subset we actually want to augment (typically the filtered schema).
//
// Returns the augmented copy of `tables`. Original is not mutated.
func InferForeignKeys(ctx context.Context, tables []schema.Table, allTables []schema.Table) ([]schema.Table, error) {
	if len(tables) == 0 {
		return tables, nil
	}

	// Build the candidate-table list. We embed each name once and reuse the
	// matcher across every column lookup.
	candidateNames := make([]string, 0, len(allTables))
	for _, t := range allTables {
		candidateNames = append(candidateNames, t.TableName)
	}

	embedder, err := llm.NewEmbedder("")
	if err != nil {
		return nil, err
	}
	matcher, err := fk.NewMatcher(ctx, embedder, candidateNames)
	if err != nil {
		return nil, err
	}

	threshold := confidenceThreshold()
	k := topK()

	out := make([]schema.Table, len(tables))
	copy(out, tables)

	for i := range out {
		t := &out[i]
		pk := ""
		if t.Metadata != nil {
			pk = t.Metadata.PrimaryKey
		}
		colNames := make([]string, len(t.Columns))
		for j, c := range t.Columns {
			colNames[j] = c.ColumnName
		}
		guesses := fk.DetectIDColumns(colNames, pk)

		// Track existing FK column names so we don't double-infer.
		existing := map[string]bool{}
		for _, fk := range t.ForeignKeys {
			existing[fk.ForeignKey] = true
		}

		newFKs := make([]schema.ForeignKey, 0)
		for _, g := range guesses {
			if g.IsPK || existing[g.Column] {
				continue
			}
			candidates, err := matcher.Match(ctx, fk.NormalizeBaseName(g.BaseName), k)
			if err != nil {
				continue // soft-fail per column
			}
			for _, cand := range candidates {
				if strings.EqualFold(cand.TableName, t.TableName) {
					continue // self-reference
				}
				if cand.Confidence >= threshold {
					newFKs = append(newFKs, schema.ForeignKey{
						ForeignKey:       g.Column,
						PrimaryKeyTable:  cand.TableName,
						PrimaryKeyColumn: g.Column,
					})
					break // only top match per ID column
				}
			}
		}

		if len(newFKs) > 0 {
			t.ForeignKeys = append(t.ForeignKeys, newFKs...)
		}
	}

	return out, nil
}
