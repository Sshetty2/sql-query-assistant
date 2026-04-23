package nodes

import (
	"context"
	"os"
	"testing"

	"github.com/joho/godotenv"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

// TestInferForeignKeys_Live exercises the node against real OpenAI embeddings.
// Skipped without an API key.
//
// Synthetic schema: "tb_Customers" + "tb_Orders" with no explicit FKs.
// tb_Orders has a `CustomerID` column. Inference should propose
// CustomerID → tb_Customers (high cosine similarity).
func TestInferForeignKeys_Live(t *testing.T) {
	loadFKEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("OPENAI_API_KEY required for embeddings")
	}

	tables := []schema.Table{
		{
			TableName: "tb_Customers",
			Columns: []schema.Column{
				{ColumnName: "CustomerID", DataType: "INTEGER"},
				{ColumnName: "Name", DataType: "NVARCHAR(40)"},
			},
			Metadata: &schema.TableMetadata{PrimaryKey: "CustomerID"},
		},
		{
			TableName: "tb_Orders",
			Columns: []schema.Column{
				{ColumnName: "OrderID", DataType: "INTEGER"},
				{ColumnName: "CustomerID", DataType: "INTEGER"},
				{ColumnName: "Total", DataType: "DECIMAL(10, 2)"},
			},
			Metadata: &schema.TableMetadata{PrimaryKey: "OrderID"},
		},
		{
			TableName: "tb_Products",
			Columns: []schema.Column{
				{ColumnName: "ProductID", DataType: "INTEGER"},
				{ColumnName: "Name", DataType: "NVARCHAR(40)"},
			},
			Metadata: &schema.TableMetadata{PrimaryKey: "ProductID"},
		},
	}

	ctx := context.Background()
	got, err := InferForeignKeys(ctx, tables, tables)
	if err != nil {
		t.Fatalf("infer: %v", err)
	}

	// Find tb_Orders in the output.
	var orders schema.Table
	for _, t := range got {
		if t.TableName == "tb_Orders" {
			orders = t
			break
		}
	}
	t.Logf("tb_Orders FKs after inference: %+v", orders.ForeignKeys)
	if len(orders.ForeignKeys) == 0 {
		t.Fatalf("expected at least one inferred FK on tb_Orders")
	}
	// Find the CustomerID FK
	var customerFK *schema.ForeignKey
	for i := range orders.ForeignKeys {
		if orders.ForeignKeys[i].ForeignKey == "CustomerID" {
			customerFK = &orders.ForeignKeys[i]
			break
		}
	}
	if customerFK == nil {
		t.Fatal("no FK inferred for CustomerID")
	}
	if customerFK.PrimaryKeyTable != "tb_Customers" {
		t.Errorf("CustomerID should resolve to tb_Customers, got %q", customerFK.PrimaryKeyTable)
	}
}

func TestInferForeignKeys_DisabledByDefault(t *testing.T) {
	if InferForeignKeysEnabled() {
		t.Error("INFER_FOREIGN_KEYS should default to false")
	}
	t.Setenv("INFER_FOREIGN_KEYS", "true")
	if !InferForeignKeysEnabled() {
		t.Error("env override didn't take effect")
	}
}

// loadFKEnv mirrors loadRepoEnv from filter_schema_test.go but loads .env
// from the same root path. We don't share the helper because go test packages
// can't see each other's *_test.go files — only the production code.
func loadFKEnv(t *testing.T) {
	// Walk up from this test file's location looking for .env (4 levels up).
	for _, p := range []string{"../../../../.env", "../../../.env", "../../.env"} {
		if err := godotenv.Load(p); err == nil {
			return
		}
	}
	t.Logf("no .env found")
}
