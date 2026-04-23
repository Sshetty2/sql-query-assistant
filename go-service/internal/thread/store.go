// Package thread persists per-query workflow state to a JSON file shared with
// the Python service. The on-disk shape matches utils/thread_manager.py exactly
// so both services can read each other's threads.
//
// File: <repo-root>/thread_states.json
//
//	{ "threads": { "<thread_id>": Thread, ... } }
//
// We use a process-local mutex around read-modify-write cycles. Cross-process
// safety is best-effort — if the Python and Go services run simultaneously
// against the same file, the last writer wins on each save. That's the same
// guarantee the Python service makes today.
package thread

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/google/uuid"
)

// Thread mirrors Python's per-thread structure.
type Thread struct {
	ThreadID      string  `json:"thread_id"`
	OriginalQuery string  `json:"original_query"`
	CreatedAt     string  `json:"created_at"`
	LastUpdated   string  `json:"last_updated"`
	Queries       []Query `json:"queries"`
}

// Query is one execution within a thread. `State` is intentionally a free-form
// map so we don't have to mirror every Python TypedDict field — callers pick
// the keys they care about.
type Query struct {
	QueryID      string         `json:"query_id"`
	Timestamp    string         `json:"timestamp"`
	UserQuestion string         `json:"user_question"`
	State        map[string]any `json:"state"`
}

type fileShape struct {
	Threads map[string]*Thread `json:"threads"`
}

// Store wraps the on-disk file with a mutex.
type Store struct {
	path string
	mu   sync.Mutex
}

// New returns a Store that reads and writes the project's thread_states.json.
// We walk up from the current directory until we find a sibling that contains
// thread_states.json so the service works whether launched from the repo root
// or from go-service/.
func New() (*Store, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return nil, err
	}
	dir := cwd
	for i := 0; i < 6; i++ {
		candidate := filepath.Join(dir, "thread_states.json")
		if _, err := os.Stat(candidate); err == nil {
			return &Store{path: candidate}, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	// Fall back to a fresh file at cwd. Reading will return an empty shape.
	return &Store{path: filepath.Join(cwd, "thread_states.json")}, nil
}

// NewAt is a test escape hatch.
func NewAt(path string) *Store {
	return &Store{path: path}
}

// CreateThread allocates a new thread_id and persists an empty thread.
func (s *Store) CreateThread(originalQuery string) (string, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	t := &Thread{
		ThreadID:      uuid.NewString(),
		OriginalQuery: originalQuery,
		CreatedAt:     now,
		LastUpdated:   now,
		Queries:       []Query{},
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	shape, err := s.readLocked()
	if err != nil {
		return "", err
	}
	shape.Threads[t.ThreadID] = t
	if err := s.writeLocked(shape); err != nil {
		return "", err
	}
	return t.ThreadID, nil
}

// SaveQueryState appends a query record to a thread. Returns the new query_id.
// State is whatever the caller chooses to persist; we don't validate the shape.
func (s *Store) SaveQueryState(threadID, userQuestion string, state map[string]any) (string, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	q := Query{
		QueryID:      uuid.NewString(),
		Timestamp:    now,
		UserQuestion: userQuestion,
		State:        state,
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	shape, err := s.readLocked()
	if err != nil {
		return "", err
	}
	t, ok := shape.Threads[threadID]
	if !ok {
		return "", fmt.Errorf("thread %s not found", threadID)
	}
	t.Queries = append(t.Queries, q)
	t.LastUpdated = now
	if err := s.writeLocked(shape); err != nil {
		return "", err
	}
	return q.QueryID, nil
}

// GetLatestQueryState returns the most recent query state for a thread.
func (s *Store) GetLatestQueryState(threadID string) (*Query, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	shape, err := s.readLocked()
	if err != nil {
		return nil, err
	}
	t, ok := shape.Threads[threadID]
	if !ok || len(t.Queries) == 0 {
		return nil, errors.New("no queries for thread")
	}
	q := t.Queries[len(t.Queries)-1]
	return &q, nil
}

func (s *Store) readLocked() (*fileShape, error) {
	data, err := os.ReadFile(s.path)
	if errors.Is(err, os.ErrNotExist) {
		return &fileShape{Threads: map[string]*Thread{}}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", s.path, err)
	}
	if len(data) == 0 {
		return &fileShape{Threads: map[string]*Thread{}}, nil
	}
	var shape fileShape
	if err := json.Unmarshal(data, &shape); err != nil {
		return nil, fmt.Errorf("decode %s: %w", s.path, err)
	}
	if shape.Threads == nil {
		shape.Threads = map[string]*Thread{}
	}
	return &shape, nil
}

func (s *Store) writeLocked(shape *fileShape) error {
	// Write to a sibling tmp file then rename — keeps the file consistent if we crash mid-write.
	raw, err := json.MarshalIndent(shape, "", "  ")
	if err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}
