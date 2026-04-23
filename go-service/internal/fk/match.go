package fk

import (
	"context"
	"fmt"
	"strings"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
	"github.com/sachit/sql-query-assistant/go-service/internal/vector"
)

// Candidate is a possible target table for an inferred FK, with a confidence
// score in [0, 1] derived from cosine similarity of the column's base name
// against the table name.
type Candidate struct {
	TableName  string
	Confidence float32
}

// Matcher embeds table names once and answers FK target queries cheaply for
// every column that needs inference. Callers create one Matcher per query.
type Matcher struct {
	embedder llm.Embedder
	store    *vector.Store[string]
	tables   []string
}

// NewMatcher embeds the candidate table names and returns a Matcher ready to
// score base-name queries. Candidate names are normalized before embedding
// (strip `tb_` / `_t` / `Tbl` prefixes and pluralization) so semantic matches
// like "Customer" ↔ "tb_Customers" don't get dragged down by table-naming
// conventions the LLM doesn't care about.
func NewMatcher(ctx context.Context, embedder llm.Embedder, tables []string) (*Matcher, error) {
	if len(tables) == 0 {
		return nil, fmt.Errorf("no tables provided")
	}
	if embedder == nil {
		return nil, fmt.Errorf("nil embedder")
	}

	normalized := make([]string, len(tables))
	for i, t := range tables {
		normalized[i] = normalizeTableName(t)
	}

	embeddings, err := embedder.Embed(ctx, normalized)
	if err != nil {
		return nil, fmt.Errorf("embed tables: %w", err)
	}
	store := vector.NewStore[string]()
	for i, t := range tables {
		store.Add(vector.Doc[string]{Text: normalized[i], Metadata: t}, embeddings[i])
	}
	return &Matcher{embedder: embedder, store: store, tables: tables}, nil
}

// normalizeTableName strips the prefixes/suffixes commonly seen in SQL
// schemas that don't add semantic meaning. Keeps the result close to a
// natural-language noun so embedding similarity reflects intent.
func normalizeTableName(s string) string {
	s = strings.TrimSpace(s)
	for _, prefix := range []string{"tb_", "tbl_", "TB_", "Tbl"} {
		s = strings.TrimPrefix(s, prefix)
	}
	for _, suffix := range []string{"_tbl", "_tab", "Tbl"} {
		s = strings.TrimSuffix(s, suffix)
	}
	// Naive plural-strip — embeddings handle "customer" ≈ "customers" fine
	// but the cosine drops a few percent without this. We only strip a single
	// trailing 's' to avoid wrecking words like "address".
	if strings.HasSuffix(s, "s") && !strings.HasSuffix(s, "ss") {
		s = strings.TrimSuffix(s, "s")
	}
	return s
}

// Match scores each candidate table against `baseName` and returns the top-k
// matches. Caller filters by `Confidence >= threshold` if it wants only
// high-quality matches.
func (m *Matcher) Match(ctx context.Context, baseName string, k int) ([]Candidate, error) {
	if baseName == "" {
		return nil, fmt.Errorf("empty base name")
	}
	queryVecs, err := m.embedder.Embed(ctx, []string{baseName})
	if err != nil {
		return nil, fmt.Errorf("embed base name: %w", err)
	}
	if len(queryVecs) == 0 {
		return nil, fmt.Errorf("embedder returned no vectors")
	}
	results, err := m.store.Search(queryVecs[0], k)
	if err != nil {
		return nil, err
	}
	out := make([]Candidate, 0, len(results))
	for _, r := range results {
		// Skip exact-name self-matches when baseName equals the table's own name
		// (e.g. tb_Company.CompanyID with the company table's own PK doesn't
		// need an FK to itself). The caller passes its own table name in to
		// help filter; here we just expose the raw result and let the caller decide.
		out = append(out, Candidate{TableName: r.Doc.Metadata, Confidence: r.Score})
	}
	return out, nil
}

// NormalizeBaseName strips common suffixes / lowercases for comparison. We
// don't normalize aggressively because the embedding model handles synonyms
// fine — this is just to drop trailing "Tbl"/"_t" pseudo-suffixes some
// production schemas use.
func NormalizeBaseName(s string) string {
	s = strings.TrimSpace(s)
	for _, suffix := range []string{"Tbl", "tbl", "_t", "_tab"} {
		s = strings.TrimSuffix(s, suffix)
	}
	return s
}
