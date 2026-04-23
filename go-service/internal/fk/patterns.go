// Package fk infers foreign-key relationships from column-naming patterns
// and vector similarity over table names. Used as an optional workflow node
// for production schemas without explicit FK constraints.
//
// Mirrors database/infer_foreign_keys.py from the Python service.
package fk

import "regexp"

// idPatterns matches the common ways production schemas spell foreign-key
// columns. Order matters: case-sensitive variants take precedence to keep
// PascalCase/snake_case distinct in `BaseName`.
var idPatterns = []*regexp.Regexp{
	regexp.MustCompile(`^(.+)ID$`),  // CompanyID, ApplicationID
	regexp.MustCompile(`^(.+)Id$`),  // TagId, UserId
	regexp.MustCompile(`^(.+)_ID$`), // Tag_ID
	regexp.MustCompile(`^(.+)_Id$`), // Tag_Id
	regexp.MustCompile(`^(.+)_id$`), // tag_id
}

// IDColumnGuess is one column that looks like a FK candidate. BaseName is the
// portion before the trailing ID — used as the embedding query when matching
// against candidate tables.
type IDColumnGuess struct {
	Column   string
	BaseName string
	IsPK     bool // true when this is the table's own primary key (don't infer FK to self)
}

// DetectIDColumns walks a table's columns and returns every one whose name
// looks like a foreign-key reference. The returned BaseName is what we'll
// look up against table names via embeddings.
//
// `pkColumn` is the table's own primary key (or "" if unknown) so we can flag
// self-references.
func DetectIDColumns(columns []string, pkColumn string) []IDColumnGuess {
	var out []IDColumnGuess
	for _, col := range columns {
		for _, re := range idPatterns {
			m := re.FindStringSubmatch(col)
			if len(m) > 1 {
				out = append(out, IDColumnGuess{
					Column:   col,
					BaseName: m[1],
					IsPK:     col == pkColumn,
				})
				break
			}
		}
	}
	return out
}
