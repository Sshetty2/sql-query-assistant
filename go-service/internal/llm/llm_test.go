package llm

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/joho/godotenv"

	m "github.com/sachit/sql-query-assistant/go-service/internal/models"
)

// loadRepoEnv loads ../../../.env relative to this test file so live tests can
// pick up API keys without requiring shell exports.
func loadRepoEnv(t *testing.T) {
	_, here, _, _ := runtime.Caller(0)
	envPath := filepath.Join(filepath.Dir(here), "..", "..", "..", ".env")
	if err := godotenv.Load(envPath); err != nil {
		t.Logf("no .env loaded (%s): %v", envPath, err)
	}
}

func TestResolveModel(t *testing.T) {
	cases := []struct {
		name              string
		input             string
		wantProvider      string
		wantModelContains string
	}{
		{"alias", "claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5-20250929"},
		{"raw claude", "claude-sonnet-4-6", "anthropic", "claude-sonnet-4-6"},
		{"raw gpt", "gpt-4o-mini", "openai", "gpt-4o-mini"},
		{"raw o3", "o3-mini", "openai", "o3-mini"},
		{"unknown -> openai", "weird-model", "openai", "weird-model"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p, m := ResolveModel(tc.input)
			if p != tc.wantProvider {
				t.Errorf("provider got %q want %q", p, tc.wantProvider)
			}
			if !strings.Contains(m, tc.wantModelContains) {
				t.Errorf("model got %q want contains %q", m, tc.wantModelContains)
			}
		})
	}
}

func TestModelForStage(t *testing.T) {
	loadRepoEnv(t)
	model := ModelForStage(StagePlanning)
	if model == "" {
		t.Skip("REMOTE_MODEL_PLANNING / AI_MODEL not set; skipping")
	}
	t.Logf("planning stage model: %s", model)
}

// TestPlannerSchemaGeneration verifies invopop/jsonschema produces a usable
// JSON Schema for PlannerOutput. We just check key shape — full conformance
// is tested implicitly when Anthropic/OpenAI accept the schema.
func TestPlannerSchemaGeneration(t *testing.T) {
	schema, err := m.PlannerOutputSchema()
	if err != nil {
		t.Fatalf("schema gen: %v", err)
	}
	if schema["type"] != "object" {
		t.Fatalf("expected top-level object schema, got: %v", schema["type"])
	}
	props, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatalf("expected properties map")
	}
	for _, required := range []string{"decision", "intent_summary", "selections"} {
		if _, ok := props[required]; !ok {
			t.Errorf("schema missing required field %q", required)
		}
	}
}

// TestStructuredOutput_Live calls the real LLM provider configured for the
// planning stage and asks it to emit a PlannerOutput for a trivial question.
// The point is parity proof, not assertion correctness — we only require
// that the provider accepts the schema and returns a decodable response.
func TestStructuredOutput_Live(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("skipping live LLM test in -short mode")
	}
	if os.Getenv("ANTHROPIC_API_KEY") == "" && os.Getenv("OPENAI_API_KEY") == "" {
		t.Skip("no API keys; skipping live LLM test")
	}

	client, err := NewForStage(StagePlanning)
	if err != nil {
		t.Skipf("no client for planning stage: %v", err)
	}

	schema, err := m.PlannerOutputSchema()
	if err != nil {
		t.Fatalf("schema: %v", err)
	}

	msgs := []Message{
		{Role: RoleSystem, Content: "You are a SQL query planner. Use the provided tool to return a structured plan."},
		{Role: RoleUser, Content: `Schema:
- table customers (CustomerId INT, FirstName NVARCHAR, LastName NVARCHAR, Country NVARCHAR)

Question: List the first names of every customer in the USA.

Plan a SELECT against the customers table, projecting FirstName, with a filter Country='USA'. Use decision='proceed'.`},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	var plan m.PlannerOutput
	if err := client.StructuredOutput(ctx, msgs, schema, "PlannerOutput", &plan); err != nil {
		t.Fatalf("structured: %v", err)
	}

	t.Logf("decision: %s", plan.Decision)
	t.Logf("intent: %s", plan.IntentSummary)
	t.Logf("selections: %d", len(plan.Selections))
	pretty, _ := json.MarshalIndent(plan, "", "  ")
	t.Logf("plan:\n%s", pretty)

	if plan.Decision != m.DecisionProceed {
		t.Errorf("expected decision=proceed, got %q", plan.Decision)
	}
	if len(plan.Selections) == 0 {
		t.Errorf("expected at least one selection")
	}
}
