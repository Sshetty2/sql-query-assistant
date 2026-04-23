// Package logger centralises the slog setup and provides a small set of helpers
// the rest of the service uses. Equivalent to utils/logger.py + utils/logging_config.py
// in the Python service: env-driven level, JSON output, request-scoped fields.
//
// We keep the API minimal:
//
//	logger.Init()                            // call once at startup
//	logger.For(ctx).Info("msg", "k", "v")    // request-scoped logger
//	ctx = logger.WithFields(ctx, "thread_id", id, "query_id", qid)
//
// `slog.Default()` is also configured by Init(), so package-level
// `slog.Info(...)` calls inherit the same handler.
package logger

import (
	"context"
	"io"
	"log/slog"
	"os"
	"strings"
)

type ctxKey struct{}

// Init configures the default slog logger. Reads LOG_LEVEL (debug/info/warn/error,
// default info) and LOG_FORMAT (json/text, default json). Returns the configured
// logger so the caller can also use it directly if needed.
func Init() *slog.Logger {
	return InitTo(os.Stdout)
}

// InitTo lets tests inject an alternative writer (e.g. bytes.Buffer).
func InitTo(w io.Writer) *slog.Logger {
	level := parseLevel(os.Getenv("LOG_LEVEL"))
	opts := &slog.HandlerOptions{Level: level}

	var h slog.Handler
	switch strings.ToLower(os.Getenv("LOG_FORMAT")) {
	case "text":
		h = slog.NewTextHandler(w, opts)
	default:
		h = slog.NewJSONHandler(w, opts)
	}
	l := slog.New(h)
	slog.SetDefault(l)
	return l
}

func parseLevel(s string) slog.Level {
	switch strings.ToLower(s) {
	case "debug":
		return slog.LevelDebug
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}

// WithFields returns a child context carrying additional structured fields
// that For(ctx) will attach to every log record. Keys/values follow slog.With
// conventions ("k1", v1, "k2", v2, …).
func WithFields(ctx context.Context, kv ...any) context.Context {
	parent := fromCtx(ctx)
	child := parent.With(kv...)
	return context.WithValue(ctx, ctxKey{}, child)
}

// For returns a logger scoped to the given context. Falls back to slog.Default()
// when the context carries no logger — never returns nil.
func For(ctx context.Context) *slog.Logger {
	return fromCtx(ctx)
}

func fromCtx(ctx context.Context) *slog.Logger {
	if ctx == nil {
		return slog.Default()
	}
	if v, ok := ctx.Value(ctxKey{}).(*slog.Logger); ok && v != nil {
		return v
	}
	return slog.Default()
}
