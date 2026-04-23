package db

import (
	"context"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
)

// TestSQLiteConcurrentReads mirrors tests/unit/test_sqlite_threading.py —
// confirms the Go service handles parallel SQLite reads without
// "database is locked" errors. modernc.org/sqlite + database/sql connection
// pool should serialize writes safely; we test the read path because that's
// what the workflow actually does.
func TestSQLiteConcurrentReads(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
	_, here, _, _ := runtime.Caller(0)
	dbPath := filepath.Join(filepath.Dir(here), "..", "..", "..", "databases", "demo_db_1.db")

	conn, err := OpenSQLite(dbPath)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer conn.Close()

	const goroutines = 10
	const queriesPerGoroutine = 5
	var wg sync.WaitGroup
	errs := make(chan error, goroutines*queriesPerGoroutine)

	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < queriesPerGoroutine; j++ {
				rows, err := conn.QueryContext(context.Background(), "SELECT COUNT(*) FROM customers")
				if err != nil {
					errs <- err
					return
				}
				rows.Close()
			}
		}()
	}
	wg.Wait()
	close(errs)

	for err := range errs {
		t.Errorf("concurrent read failed: %v", err)
	}
}
