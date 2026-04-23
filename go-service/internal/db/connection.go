package db

import (
	"database/sql"
	"fmt"
	"os"
	"strings"

	_ "modernc.org/sqlite" // pure-Go SQLite driver — no CGO required
)

// OpenSQLite opens a SQLite database in read-write mode using the pure-Go modernc.org/sqlite driver.
// Pure-Go avoids CGO toolchain requirements on Windows and keeps the build a single static binary.
func OpenSQLite(path string) (*sql.DB, error) {
	conn, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open sqlite %s: %w", path, err)
	}
	conn.SetMaxOpenConns(1) // mirror sqlite3.connect default; cheap and avoids busy errors on writes
	return conn, nil
}

// OpenSQLServer opens a SQL Server connection from environment variables, mirroring
// build_connection_string() in database/connection.py.
func OpenSQLServer() (*sql.DB, error) {
	server := os.Getenv("DB_SERVER")
	dbName := os.Getenv("DB_NAME")
	user := os.Getenv("DB_USER")
	pass := os.Getenv("DB_PASSWORD")

	if server == "" || dbName == "" {
		return nil, fmt.Errorf("DB_SERVER and DB_NAME must be set when USE_TEST_DB is not true")
	}

	parts := []string{
		"server=" + server,
		"database=" + dbName,
	}
	if user != "" && pass != "" {
		parts = append(parts, "user id="+user, "password="+pass)
	} else {
		parts = append(parts, "trusted_connection=yes")
	}
	connStr := strings.Join(parts, ";")

	conn, err := sql.Open("sqlserver", connStr)
	if err != nil {
		return nil, fmt.Errorf("open sqlserver: %w", err)
	}
	return conn, nil
}

// Open returns a connection appropriate for the current environment, honoring USE_TEST_DB and db_id
// the same way database/connection.py:get_pyodbc_connection does.
func Open(dbID string) (*sql.DB, error) {
	if strings.ToLower(os.Getenv("USE_TEST_DB")) == "true" {
		var path string
		var err error
		if dbID != "" {
			path, err = ResolveDemoPath(dbID)
		} else {
			path, err = SampleDBPath()
		}
		if err != nil {
			return nil, err
		}
		return OpenSQLite(path)
	}
	return OpenSQLServer()
}
