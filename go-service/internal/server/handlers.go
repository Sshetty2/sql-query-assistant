package server

import (
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/sachit/sql-query-assistant/go-service/internal/db"
	"github.com/sachit/sql-query-assistant/go-service/internal/schema"
)

func useTestDB() bool {
	return strings.ToLower(os.Getenv("USE_TEST_DB")) == "true"
}

func (s *Server) listDatabases(c *gin.Context) {
	if !useTestDB() {
		c.JSON(http.StatusOK, []any{})
		return
	}

	entries, err := db.LoadRegistry()
	if err != nil {
		s.logger.Warn("registry load failed; returning empty list", "err", err)
		c.JSON(http.StatusOK, []any{})
		return
	}
	c.JSON(http.StatusOK, entries)
}

func (s *Server) getDatabaseSchema(c *gin.Context) {
	dbID := c.Param("db_id")

	dbPath, err := db.ResolveDemoPath(dbID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"detail": err.Error()})
		return
	}

	conn, err := db.OpenSQLite(dbPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to open database: " + err.Error()})
		return
	}
	defer conn.Close()

	tables, err := schema.IntrospectSQLite(c.Request.Context(), conn)
	if err != nil {
		s.logger.Error("introspection failed", "db_id", dbID, "err", err)
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "schema introspection failed: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, tables)
}
