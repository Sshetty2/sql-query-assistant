package main

import (
	"net/http"
	"os"

	"github.com/joho/godotenv"

	"github.com/sachit/sql-query-assistant/go-service/internal/logger"
	"github.com/sachit/sql-query-assistant/go-service/internal/server"
)

func main() {
	// Best-effort .env load — falls back silently if the file is missing.
	_ = godotenv.Load()
	_ = godotenv.Load("../.env")

	log := logger.Init()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8001"
	}

	srv := server.New(log)
	addr := ":" + port
	log.Info("starting go-service", "addr", addr)
	if err := http.ListenAndServe(addr, srv.Handler()); err != nil {
		log.Error("server failed", "err", err)
		os.Exit(1)
	}
}
