package fk

import "testing"

func TestDetectIDColumns(t *testing.T) {
	// Bare "ID" doesn't match (.+)ID since the prefix must be non-empty —
	// matches Python's behavior. We expect only the prefixed columns.
	cols := []string{"ID", "CompanyID", "Name", "TagId", "user_id", "Description"}
	got := DetectIDColumns(cols, "ID")
	if len(got) != 3 {
		t.Fatalf("expected 3 ID columns, got %d: %+v", len(got), got)
	}
	want := map[string]string{
		"CompanyID": "Company",
		"TagId":     "Tag",
		"user_id":   "user",
	}
	for _, g := range got {
		base, ok := want[g.Column]
		if !ok {
			t.Errorf("unexpected detection: %+v", g)
			continue
		}
		if g.BaseName != base {
			t.Errorf("base name for %q got %q, want %q", g.Column, g.BaseName, base)
		}
		if g.IsPK {
			t.Errorf("FK guess %q wrongly flagged as PK", g.Column)
		}
	}
}

func TestDetectIDColumns_PKDetection(t *testing.T) {
	// When the table's own PK matches an FK pattern, we flag it so the caller
	// can skip inferring an FK to itself (e.g. tb_Company.CompanyID where the
	// table's PK literally IS CompanyID).
	got := DetectIDColumns([]string{"CompanyID", "Name"}, "CompanyID")
	if len(got) != 1 {
		t.Fatalf("expected 1 detection, got %d", len(got))
	}
	if !got[0].IsPK {
		t.Errorf("CompanyID should be flagged as PK when it matches the table's PK")
	}
}

func TestDetectIDColumns_RejectsNonPattern(t *testing.T) {
	got := DetectIDColumns([]string{"Email", "FirstName", "Notes"}, "")
	if len(got) != 0 {
		t.Errorf("expected no matches, got %+v", got)
	}
}

func TestNormalizeBaseName(t *testing.T) {
	cases := map[string]string{
		"Company":     "Company",
		"CompanyTbl":  "Company",
		"company_t":   "company",
		"  Customer ": "Customer",
	}
	for in, want := range cases {
		if got := NormalizeBaseName(in); got != want {
			t.Errorf("NormalizeBaseName(%q) = %q, want %q", in, got, want)
		}
	}
}
