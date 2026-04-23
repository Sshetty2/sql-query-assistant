package chat

import (
	"testing"
	"time"
)

func TestSessions_GetCreatesIfMissing(t *testing.T) {
	s := NewSessions()
	got := s.Get("first")
	if got == nil || got.ID != "first" {
		t.Fatalf("expected new session with id 'first', got %+v", got)
	}
	if s.Len() != 1 {
		t.Errorf("len got %d want 1", s.Len())
	}
}

func TestSessions_GetReturnsSameInstance(t *testing.T) {
	s := NewSessions()
	a := s.Get("same")
	a.ToolCallCount = 5
	b := s.Get("same")
	if b.ToolCallCount != 5 {
		t.Error("Get should return the same session instance")
	}
}

func TestSessions_Reset(t *testing.T) {
	s := NewSessions()
	s.Get("temp")
	if !s.Reset("temp") {
		t.Error("Reset should return true for known session")
	}
	if s.Reset("temp") {
		t.Error("Reset should return false for already-reset session")
	}
	if s.Len() != 0 {
		t.Errorf("len got %d want 0 after reset", s.Len())
	}
}

func TestSessions_StaleEviction(t *testing.T) {
	s := NewSessions()
	old := s.Get("old")
	// Backdate so the next Get triggers stale eviction.
	old.LastUsed = time.Now().Add(-2 * sessionTTL)

	s.Get("fresh")
	// "old" should be gone; only "fresh" remains.
	if s.Len() != 1 {
		t.Errorf("expected 1 session after stale eviction, got %d", s.Len())
	}
}

func TestSessions_CapacityEviction(t *testing.T) {
	s := NewSessions()
	// Fill to capacity.
	for i := 0; i < maxSessions; i++ {
		s.Get(makeID(i))
	}
	// Adding one more should evict the oldest, keeping count at capacity.
	s.Get("over_capacity")
	if s.Len() != maxSessions {
		t.Errorf("expected %d sessions after over-capacity insert, got %d", maxSessions, s.Len())
	}
}

func makeID(n int) string {
	out := make([]byte, 0, 8)
	if n == 0 {
		return "0"
	}
	for n > 0 {
		out = append([]byte{byte('0' + n%10)}, out...)
		n /= 10
	}
	return string(out)
}
