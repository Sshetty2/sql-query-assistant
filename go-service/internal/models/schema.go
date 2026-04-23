package models

import (
	"encoding/json"

	"github.com/invopop/jsonschema"
)

// reflectSchema runs invopop/jsonschema with the inline-everything settings
// both OpenAI's structured outputs and Anthropic's forced tool-use prefer.
func reflectSchema(target any) (map[string]any, error) {
	r := &jsonschema.Reflector{
		Anonymous:                  true,
		AllowAdditionalProperties:  false,
		DoNotReference:             true,
		ExpandedStruct:             true,
		RequiredFromJSONSchemaTags: false,
	}
	s := r.Reflect(target)
	raw, err := json.Marshal(s)
	if err != nil {
		return nil, err
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// PlannerOutputSchema returns the JSON Schema for PlannerOutput. Used by every
// LLM call that produces a structured query plan.
func PlannerOutputSchema() (map[string]any, error) {
	return reflectSchema(&PlannerOutput{})
}

// TableSelectionOutputSchema returns the JSON Schema for the Stage-3 LLM in
// filter_schema (which tables are relevant + which columns).
func TableSelectionOutputSchema() (map[string]any, error) {
	return reflectSchema(&TableSelectionOutput{})
}
