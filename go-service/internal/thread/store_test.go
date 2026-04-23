package thread

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestStore_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "thread_states.json")
	s := NewAt(path)

	tid, err := s.CreateThread("show me top customers")
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if tid == "" {
		t.Fatal("empty thread id")
	}

	qid, err := s.SaveQueryState(tid, "show me top customers", map[string]any{
		"query":      "SELECT * FROM customers",
		"row_count":  5,
		"last_step":  "execute_query",
	})
	if err != nil {
		t.Fatalf("save: %v", err)
	}
	if qid == "" {
		t.Fatal("empty query id")
	}

	q, err := s.GetLatestQueryState(tid)
	if err != nil {
		t.Fatalf("get latest: %v", err)
	}
	if q.QueryID != qid {
		t.Errorf("query id mismatch: got %s want %s", q.QueryID, qid)
	}
	if q.State["row_count"].(float64) != 5 {
		t.Errorf("row_count round-trip lost data: %v", q.State["row_count"])
	}

	// Verify on-disk shape matches Python's expected layout.
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read file: %v", err)
	}
	var shape map[string]any
	if err := json.Unmarshal(raw, &shape); err != nil {
		t.Fatalf("decode: %v", err)
	}
	threads, ok := shape["threads"].(map[string]any)
	if !ok {
		t.Fatalf("missing top-level threads key, got: %v", shape)
	}
	thread, ok := threads[tid].(map[string]any)
	if !ok {
		t.Fatalf("missing thread %s", tid)
	}
	for _, key := range []string{"thread_id", "original_query", "created_at", "last_updated", "queries"} {
		if _, ok := thread[key]; !ok {
			t.Errorf("missing key %q in thread shape", key)
		}
	}
}

func TestStore_MissingFileIsEmpty(t *testing.T) {
	dir := t.TempDir()
	s := NewAt(filepath.Join(dir, "doesnotexist.json"))
	if _, err := s.GetLatestQueryState("nope"); err == nil {
		t.Error("expected error for missing thread")
	}
}
