// Package cancel manages per-session cancellation tokens for in-flight workflows.
// Mirrors server.py:_active_sessions / register_session / cancel_session — the
// goal is to let the React frontend cancel a running query when the user hits
// "stop" or starts a new one.
//
// Design:
//   - Sessions are keyed by the page-session ID the frontend supplies in the
//     `x-page-session` header (64-char hex).
//   - Each entry stores a context.CancelFunc so the workflow's derived ctx
//     trips when Cancel() is called.
//   - We cap the registry at 200 sessions and evict entries older than 10
//     minutes, matching Python's MAX_ACTIVE_SESSIONS / _SESSION_STALE_SECONDS.
//   - Registering the same session_id twice cancels the previous one — a new
//     query in the same browser tab supersedes the old one.
package cancel

import (
	"context"
	"regexp"
	"sync"
	"time"
)

const (
	maxSessions  = 200
	sessionTTL   = 10 * time.Minute
)

// pageSessionRE matches the 64-char hex format the frontend produces via
// `crypto.randomBytes(32).toString("hex")`. Anything else is treated as
// untrusted and ignored, same as Python.
var pageSessionRE = regexp.MustCompile(`^[0-9a-f]{64}$`)

// ValidateSessionID returns the session ID if it matches the expected format,
// else "". Mirrors server.py:_validate_page_session.
func ValidateSessionID(raw string) string {
	if pageSessionRE.MatchString(raw) {
		return raw
	}
	return ""
}

type entry struct {
	cancel    context.CancelFunc
	createdAt time.Time
}

// Registry tracks active workflows by session ID. Safe for concurrent use.
type Registry struct {
	mu       sync.Mutex
	sessions map[string]*entry
}

func NewRegistry() *Registry {
	return &Registry{sessions: make(map[string]*entry, maxSessions)}
}

// Register creates a child context tied to a cancel func stored under sessionID.
// If sessionID is already present, the prior workflow is cancelled first
// (matching Python behavior — a new query in the same tab pre-empts the old).
//
// Eviction policy:
//  1. Drop any entries older than the TTL.
//  2. If still at capacity, drop the oldest entry.
//
// Returns the derived context plus a cleanup func the caller should defer
// to ensure the registry doesn't leak entries on normal completion.
func (r *Registry) Register(parent context.Context, sessionID string) (context.Context, func()) {
	if sessionID == "" {
		// No session → no registry entry, just a cancellable child ctx so the
		// orchestrator can still observe ctx.Done() on parent timeout.
		ctx, cancel := context.WithCancel(parent)
		return ctx, cancel
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	now := time.Now()
	r.evictStaleLocked(now)

	if existing, ok := r.sessions[sessionID]; ok {
		existing.cancel() // pre-empt the previous query in this session
	} else if len(r.sessions) >= maxSessions {
		r.evictOldestLocked()
	}

	ctx, cancel := context.WithCancel(parent)
	r.sessions[sessionID] = &entry{cancel: cancel, createdAt: now}

	cleanup := func() {
		// Cancel + remove on normal completion. Idempotent.
		r.mu.Lock()
		defer r.mu.Unlock()
		if cur, ok := r.sessions[sessionID]; ok && cur.cancel != nil {
			cur.cancel()
			delete(r.sessions, sessionID)
		}
	}
	return ctx, cleanup
}

// Cancel triggers the cancel func for the given session, if any. Returns true
// if a session was found and cancelled.
func (r *Registry) Cancel(sessionID string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	e, ok := r.sessions[sessionID]
	if !ok {
		return false
	}
	e.cancel()
	delete(r.sessions, sessionID)
	return true
}

// Len returns the current number of tracked sessions (mostly for tests).
func (r *Registry) Len() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.sessions)
}

func (r *Registry) evictStaleLocked(now time.Time) {
	cutoff := now.Add(-sessionTTL)
	for k, v := range r.sessions {
		if v.createdAt.Before(cutoff) {
			v.cancel()
			delete(r.sessions, k)
		}
	}
}

func (r *Registry) evictOldestLocked() {
	var oldestKey string
	var oldestAt time.Time
	first := true
	for k, v := range r.sessions {
		if first || v.createdAt.Before(oldestAt) {
			oldestKey = k
			oldestAt = v.createdAt
			first = false
		}
	}
	if oldestKey != "" {
		r.sessions[oldestKey].cancel()
		delete(r.sessions, oldestKey)
	}
}
