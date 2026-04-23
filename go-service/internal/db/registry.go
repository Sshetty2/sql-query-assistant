package db

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// RegistryEntry mirrors the shape stored in databases/registry.json.
// The JSON file is the source of truth; both the Python and Go services read it.
type RegistryEntry struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	File        string `json:"file"`
}

// projectRoot walks up from the running binary's working directory until it finds
// a directory containing `databases/registry.json`. This lets the service run from
// either the repo root or `go-service/`.
func projectRoot() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := cwd
	for i := 0; i < 6; i++ {
		candidate := filepath.Join(dir, "databases", "registry.json")
		if _, err := os.Stat(candidate); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return "", fmt.Errorf("databases/registry.json not found above %s", cwd)
}

func registryPath() (string, string, error) {
	root, err := projectRoot()
	if err != nil {
		return "", "", err
	}
	return root, filepath.Join(root, "databases", "registry.json"), nil
}

// LoadRegistry returns every registry entry. Empty slice (not nil) on missing file
// so JSON serialisation matches the Python service exactly.
func LoadRegistry() ([]RegistryEntry, error) {
	_, path, err := registryPath()
	if err != nil {
		return []RegistryEntry{}, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return []RegistryEntry{}, err
	}
	var entries []RegistryEntry
	if err := json.Unmarshal(data, &entries); err != nil {
		return []RegistryEntry{}, err
	}
	return entries, nil
}

// ResolveDemoPath maps a db_id to its absolute SQLite file path, with the same
// path-traversal guard the Python implementation uses.
func ResolveDemoPath(dbID string) (string, error) {
	root, _, err := registryPath()
	if err != nil {
		return "", err
	}
	entries, err := LoadRegistry()
	if err != nil {
		return "", err
	}
	databasesDir := filepath.Join(root, "databases")

	for _, entry := range entries {
		if entry.ID != dbID {
			continue
		}
		candidate := filepath.Join(databasesDir, entry.File)
		realCandidate, err := filepath.EvalSymlinks(candidate)
		if err != nil {
			realCandidate = candidate
		}
		realDir, err := filepath.EvalSymlinks(databasesDir)
		if err != nil {
			realDir = databasesDir
		}
		if !strings.HasPrefix(realCandidate, realDir) {
			return "", fmt.Errorf("invalid database path for %s", dbID)
		}
		if _, err := os.Stat(candidate); err != nil {
			return "", fmt.Errorf("database file not found: %s", candidate)
		}
		return candidate, nil
	}
	return "", fmt.Errorf("unknown database ID: %s", dbID)
}

// SampleDBPath returns the path to the legacy single-DB sample-db.db at the repo root.
func SampleDBPath() (string, error) {
	root, err := projectRoot()
	if err != nil {
		return "", err
	}
	path := filepath.Join(root, "sample-db.db")
	if _, err := os.Stat(path); err != nil {
		return "", err
	}
	return path, nil
}
