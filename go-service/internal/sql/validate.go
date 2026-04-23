package sql

import (
	"fmt"
	"regexp"
	"strings"
)

// destructiveKeywords lists everything we refuse to execute when a user POSTs
// raw SQL to /query/execute-sql. The list mirrors the Python service's intent:
// reads only, never mutations or DDL.
var destructiveKeywords = []string{
	"INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
	"DROP", "TRUNCATE", "CREATE", "ALTER", "RENAME",
	"GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
	"REPLACE", "ATTACH", "DETACH", "VACUUM", "REINDEX",
	"BACKUP", "RESTORE",
}

// stripCommentsRE matches `-- ...` line comments and `/* ... */` block comments.
// We strip them first so a comment can't smuggle a banned keyword past the check.
var stripCommentsRE = regexp.MustCompile(`(?s)(--[^\n]*)|(/\*.*?\*/)`)

// IsSelectOnly returns nil if `query` is a single SELECT-style read, or an
// error describing the violation. Used by the /query/execute-sql endpoint.
//
// We accept:
//   - SELECT ... (with optional leading WITH ... CTE)
//
// We reject:
//   - any of `destructiveKeywords` appearing as a top-level statement word
//   - multiple statements (even if all SELECTs)
//   - empty / whitespace-only input
func IsSelectOnly(query string) error {
	trimmed := strings.TrimSpace(query)
	if trimmed == "" {
		return fmt.Errorf("empty SQL")
	}

	// Strip comments before keyword scanning so they can't hide intent.
	noComments := stripCommentsRE.ReplaceAllString(trimmed, " ")
	upper := strings.ToUpper(noComments)

	// Reject multiple statements. We detect a `;` followed by more non-whitespace.
	if idx := strings.Index(upper, ";"); idx >= 0 {
		rest := strings.TrimSpace(upper[idx+1:])
		if rest != "" {
			return fmt.Errorf("multiple statements not allowed")
		}
	}

	// First non-whitespace word must be SELECT or WITH (CTE leading into SELECT).
	first := firstWord(upper)
	if first != "SELECT" && first != "WITH" {
		return fmt.Errorf("only SELECT statements are allowed (got %q)", first)
	}

	// Scan for any destructive keyword at word boundaries.
	for _, kw := range destructiveKeywords {
		// `\b` word boundary keeps us from flagging substrings (e.g. CALCULATED ≠ CALL).
		re := regexp.MustCompile(`\b` + kw + `\b`)
		if re.MatchString(upper) {
			return fmt.Errorf("disallowed keyword %q in SQL", kw)
		}
	}
	return nil
}

func firstWord(s string) string {
	for i := 0; i < len(s); i++ {
		if s[i] != ' ' && s[i] != '\t' && s[i] != '\n' && s[i] != '\r' {
			j := i
			for j < len(s) && s[j] != ' ' && s[j] != '\t' && s[j] != '\n' && s[j] != '\r' && s[j] != '(' {
				j++
			}
			return s[i:j]
		}
	}
	return ""
}
