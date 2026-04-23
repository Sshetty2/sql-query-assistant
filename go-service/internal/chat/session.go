// Package chat implements the conversational data-assistant: in-memory
// session storage, tool definitions for the agentic loop, and the loop itself.
//
// Sessions are keyed by `chat_session_id`, a frontend-generated string that
// usually takes the form `<thread_id>:<query_id>`. They hold message history
// and a per-session counter of how many tool calls the LLM has used (to
// enforce the MAX_CHAT_TOOL_CALLS budget that mirrors the Python service).
package chat

import (
	"sync"
	"time"

	"github.com/sachit/sql-query-assistant/go-service/internal/llm"
)

const (
	maxSessions = 200
	sessionTTL  = 30 * time.Minute
)

// Session is a single chat conversation's state.
type Session struct {
	ID            string
	Messages      []llm.Message
	ToolCallCount int
	LastUsed      time.Time
}

// Sessions is a process-local registry of in-flight chat sessions. Mirrors
// `_chat_sessions` in agent/chat_agent.py — ephemeral, lost on restart.
type Sessions struct {
	mu sync.Mutex
	m  map[string]*Session
}

func NewSessions() *Sessions {
	return &Sessions{m: make(map[string]*Session, maxSessions)}
}

// Get returns the session for `id`, creating an empty one if it doesn't exist.
// Always touches LastUsed so eviction picks the truly oldest sessions.
func (s *Sessions) Get(id string) *Session {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	s.evictStaleLocked(now)

	sess, ok := s.m[id]
	if !ok {
		if len(s.m) >= maxSessions {
			s.evictOldestLocked()
		}
		sess = &Session{ID: id, Messages: []llm.Message{}}
		s.m[id] = sess
	}
	sess.LastUsed = now
	return sess
}

// Reset drops the session entirely. Mirrors POST /query/chat/reset.
func (s *Sessions) Reset(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.m[id]; !ok {
		return false
	}
	delete(s.m, id)
	return true
}

// Len reports how many sessions are tracked (mostly for tests).
func (s *Sessions) Len() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.m)
}

func (s *Sessions) evictStaleLocked(now time.Time) {
	cutoff := now.Add(-sessionTTL)
	for id, sess := range s.m {
		if sess.LastUsed.Before(cutoff) {
			delete(s.m, id)
		}
	}
}

func (s *Sessions) evictOldestLocked() {
	var oldestID string
	var oldestAt time.Time
	first := true
	for id, sess := range s.m {
		if first || sess.LastUsed.Before(oldestAt) {
			oldestID = id
			oldestAt = sess.LastUsed
			first = false
		}
	}
	if oldestID != "" {
		delete(s.m, oldestID)
	}
}
