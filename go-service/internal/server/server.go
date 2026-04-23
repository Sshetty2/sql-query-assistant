package server

import (
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sachit/sql-query-assistant/go-service/internal/cancel"
	"github.com/sachit/sql-query-assistant/go-service/internal/chat"
	"github.com/sachit/sql-query-assistant/go-service/internal/thread"
)

type Server struct {
	engine       *gin.Engine
	logger       *slog.Logger
	threads      *thread.Store
	cancels      *cancel.Registry
	chatSessions *chat.Sessions
	chatAgent    *chat.Agent
}

func New(logger *slog.Logger) *Server {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Recovery())
	engine.Use(requestLogger())

	threads, err := thread.New()
	if err != nil {
		logger.Warn("thread store init failed; persistence disabled", "err", err)
	}

	chatSessions := chat.NewSessions()

	s := &Server{
		engine:       engine,
		logger:       logger,
		threads:      threads,
		cancels:      cancel.NewRegistry(),
		chatSessions: chatSessions,
		chatAgent:    chat.NewAgent(chatSessions, liveQueryRunner{}),
	}
	s.registerRoutes()
	return s
}

func (s *Server) Handler() http.Handler {
	return s.engine
}

func (s *Server) registerRoutes() {
	s.engine.GET("/", s.healthCheck)
	s.engine.GET("/databases", s.listDatabases)
	s.engine.GET("/databases/:db_id/schema", s.getDatabaseSchema)
	s.registerQueryRoutes()
	s.engine.POST("/cancel", s.cancelHandler)
	s.engine.POST("/query/execute-sql", s.execSQLHandler)
	s.engine.POST("/query/patch", s.patchHandler)
	s.engine.POST("/query/chat", s.chatHandler)
	s.engine.POST("/query/chat/reset", s.chatResetHandler)
}

func (s *Server) healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"message": "SQL Query Assistant API (Go) is running!"})
}
