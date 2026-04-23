package cancel

import (
	"context"
	"strings"
	"testing"
)

func TestValidateSessionID(t *testing.T) {
	good := strings.Repeat("a", 64)
	if got := ValidateSessionID(good); got != good {
		t.Errorf("good session id rejected: %q", got)
	}
	for _, bad := range []string{"", "short", strings.Repeat("a", 63), strings.Repeat("Z", 64), strings.Repeat("g", 64)} {
		if got := ValidateSessionID(bad); got != "" {
			t.Errorf("bad session id %q passed validation", bad)
		}
	}
}

func TestRegistry_RegisterAndCancel(t *testing.T) {
	r := NewRegistry()
	sid := strings.Repeat("a", 64)

	ctx, cleanup := r.Register(context.Background(), sid)
	defer cleanup()

	if r.Len() != 1 {
		t.Fatalf("expected 1 session, got %d", r.Len())
	}
	if ctx.Err() != nil {
		t.Fatalf("ctx already cancelled before Cancel(): %v", ctx.Err())
	}

	if !r.Cancel(sid) {
		t.Fatal("Cancel returned false for known session")
	}
	if ctx.Err() == nil {
		t.Fatal("ctx not cancelled after Cancel()")
	}
	if r.Len() != 0 {
		t.Errorf("expected 0 sessions after Cancel, got %d", r.Len())
	}
}

func TestRegistry_DuplicateRegisterPreemptsOld(t *testing.T) {
	r := NewRegistry()
	sid := strings.Repeat("b", 64)
	ctx1, cleanup1 := r.Register(context.Background(), sid)
	defer cleanup1()

	ctx2, cleanup2 := r.Register(context.Background(), sid)
	defer cleanup2()

	if ctx1.Err() == nil {
		t.Error("first ctx should be cancelled when second registers under same id")
	}
	if ctx2.Err() != nil {
		t.Error("second ctx should still be active")
	}
	if r.Len() != 1 {
		t.Errorf("expected 1 session (the new one), got %d", r.Len())
	}
}

func TestRegistry_EmptySessionGivesUntracked(t *testing.T) {
	r := NewRegistry()
	ctx, cleanup := r.Register(context.Background(), "")
	defer cleanup()

	if r.Len() != 0 {
		t.Errorf("empty session should not register, got len %d", r.Len())
	}
	if ctx.Err() != nil {
		t.Error("returned ctx should still be active")
	}
	cleanup()
	if ctx.Err() == nil {
		t.Error("cleanup should cancel the returned ctx")
	}
}

func TestRegistry_CancelUnknownReturnsFalse(t *testing.T) {
	r := NewRegistry()
	if r.Cancel("never_registered") {
		t.Error("Cancel of unknown session should return false")
	}
}

func TestRegistry_EvictsOldestAtCapacity(t *testing.T) {
	r := NewRegistry()
	// Fill to capacity using unique 64-hex IDs.
	for i := 0; i < maxSessions; i++ {
		id := makeID(i)
		r.Register(context.Background(), id)
	}
	if r.Len() != maxSessions {
		t.Fatalf("expected %d sessions, got %d", maxSessions, r.Len())
	}
	// Adding one more should evict the oldest, keeping us at capacity.
	r.Register(context.Background(), makeID(9999))
	if r.Len() != maxSessions {
		t.Errorf("expected %d sessions after over-capacity insert, got %d", maxSessions, r.Len())
	}
}

// makeID produces unique 64-hex session IDs for tests. We zero-pad on the right
// because the padding char must NOT collide with any hex digit ('0' is fine —
// `n=0` is still distinguishable from any positive n once we always emit at
// least one digit at position 63).
func makeID(n int) string {
	const hex = "0123456789abcdef"
	out := make([]byte, 64)
	for i := range out {
		out[i] = '0'
	}
	// Encode n in the LAST positions so length differences don't collide.
	for i := 63; n > 0 && i >= 0; i-- {
		out[i] = hex[n%16]
		n /= 16
	}
	return string(out)
}
