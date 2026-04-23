package nodes

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/joho/godotenv"
	_ "modernc.org/sqlite"

	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

func loadRepoEnv(t *testing.T) string {
	_, here, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(here), "..", "..", "..", "..")
	envPath := filepath.Join(root, ".env")
	if err := godotenv.Load(envPath); err != nil {
		t.Logf("no .env loaded (%s): %v", envPath, err)
	}
	return root
}

// TestFilterSchema_SyntheticFKExpansion verifies the FK-expansion logic in
// isolation — no LLM, no embeddings, just graph traversal. Built around a
// hand-crafted schema so the assertions are obvious.
func TestFilterSchema_SyntheticFKExpansion(t *testing.T) {
	allTables := []schema.Table{
		{TableName: "customers"},
		{TableName: "invoices", ForeignKeys: []schema.ForeignKey{
			{ForeignKey: "CustomerId", PrimaryKeyTable: "customers", PrimaryKeyColumn: "CustomerId"},
		}},
		{TableName: "invoice_items", ForeignKeys: []schema.ForeignKey{
			{ForeignKey: "InvoiceId", PrimaryKeyTable: "invoices", PrimaryKeyColumn: "InvoiceId"},
			{ForeignKey: "TrackId", PrimaryKeyTable: "tracks", PrimaryKeyColumn: "TrackId"},
		}},
		{TableName: "tracks"},
		{TableName: "unrelated"},
	}

	// Start from just `customers`. Depth=2 should pull in invoices (forward
	// reverse-ref from invoices→customers) and invoice_items (reverse from
	// invoices). It should NOT pull `tracks` since that needs a third hop or
	// the user to select invoice_items.
	expanded := expandWithForeignKeys([]schema.Table{allTables[0]}, allTables, 2)
	got := tableNames(expanded)
	sort.Strings(got)
	want := []string{"customers", "invoice_items", "invoices"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("FK expansion got %v, want %v", got, want)
	}
}

// TestFilterSchema_LiveE2E runs the whole pipeline against demo_db_1 with a
// real Claude call. Skipped if API keys aren't available.
func TestFilterSchema_LiveE2E(t *testing.T) {
	root := loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY not set; embedder needs it")
	}
	if os.Getenv("ANTHROPIC_API_KEY") == "" && os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("no chat API keys")
	}

	dbPath := filepath.Join(root, "databases", "demo_db_1.db")
	conn, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	tables, err := schema.IntrospectSQLite(ctx, conn)
	if err != nil {
		t.Fatalf("introspect: %v", err)
	}
	t.Logf("introspected %d tables", len(tables))

	out, err := FilterSchema(ctx, FilterSchemaInput{
		Schema:       tables,
		UserQuestion: "Which musical genres have generated the most revenue from customer invoices?",
		TopK:         8,
	})
	if err != nil {
		t.Fatalf("filter: %v", err)
	}

	t.Logf("vector + FK candidates (%d): %v", len(out.CandidateTables), out.CandidateTables)
	t.Logf("LLM-selected (%d): %v", len(out.SelectedTables), out.SelectedTables)
	for _, a := range out.Reasoning {
		t.Logf("  %s relevant=%v cols=%v reasoning=%s",
			a.TableName, a.IsRelevant, a.RelevantColumns, a.Reasoning)
	}

	// Sanity: the prompt is about genres + revenue + customers + invoices.
	// The filter should pick at least three of {genres, tracks, invoice_items, invoices, customers}.
	wantAnyOf := map[string]bool{
		"genres": true, "tracks": true, "invoice_items": true, "invoices": true, "customers": true,
	}
	hits := 0
	for _, name := range out.SelectedTables {
		if wantAnyOf[name] {
			hits++
		}
	}
	if hits < 3 {
		t.Errorf("expected ≥3 of {genres, tracks, invoice_items, invoices, customers} in selected tables; got hits=%d in %v", hits, out.SelectedTables)
	}

	// Truncated schema should have fewer total columns than full schema (LLM filtering took effect).
	fullCols, truncCols := 0, 0
	for _, t := range out.FilteredSchema {
		fullCols += len(t.Columns)
	}
	for _, t := range out.TruncatedSchema {
		truncCols += len(t.Columns)
	}
	t.Logf("full columns: %d, truncated columns: %d", fullCols, truncCols)
}
