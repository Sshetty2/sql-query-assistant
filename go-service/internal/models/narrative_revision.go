package models

// NarrativeRevision is the optional SQL revision the narrative LLM may emit
// alongside its summary when it spots a data-quality issue. Matches Python's
// wire field `narrative_revision` on the query response.
type NarrativeRevision struct {
	RevisedSQL  string `json:"revised_sql"`
	Explanation string `json:"explanation"`
}
