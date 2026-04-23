package vector

import "testing"

func TestStore_Search(t *testing.T) {
	s := NewStore[string]()
	s.Add(Doc[string]{Text: "exact match", Metadata: "a"}, []float32{1, 0, 0})
	s.Add(Doc[string]{Text: "perpendicular", Metadata: "b"}, []float32{0, 1, 0})
	s.Add(Doc[string]{Text: "negated", Metadata: "c"}, []float32{-1, 0, 0})

	results, err := s.Search([]float32{1, 0, 0}, 3)
	if err != nil {
		t.Fatalf("search: %v", err)
	}
	if len(results) != 3 {
		t.Fatalf("expected 3 results, got %d", len(results))
	}
	if results[0].Doc.Metadata != "a" {
		t.Errorf("expected exact-match first, got %q", results[0].Doc.Metadata)
	}
	if results[2].Doc.Metadata != "c" {
		t.Errorf("expected negated last, got %q", results[2].Doc.Metadata)
	}
}

func TestStore_KGreaterThanLen(t *testing.T) {
	s := NewStore[int]()
	s.Add(Doc[int]{Metadata: 1}, []float32{1, 0})
	results, err := s.Search([]float32{1, 0}, 10)
	if err != nil {
		t.Fatalf("search: %v", err)
	}
	if len(results) != 1 {
		t.Errorf("expected 1 result, got %d", len(results))
	}
}

func TestCosine_ZeroNorm(t *testing.T) {
	if got := cosine([]float32{0, 0}, []float32{1, 0}); got != 0 {
		t.Errorf("expected 0 for zero-norm input, got %v", got)
	}
}
