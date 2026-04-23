package logger

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func TestWithFieldsAndFor(t *testing.T) {
	var buf bytes.Buffer
	InitTo(&buf)

	ctx := WithFields(context.Background(), "thread_id", "abc", "query_id", "q1")
	For(ctx).Info("hello", "stage", "test")

	line := strings.TrimSpace(buf.String())
	var rec map[string]any
	if err := json.Unmarshal([]byte(line), &rec); err != nil {
		t.Fatalf("parse JSON: %v\nraw: %s", err, line)
	}

	for _, want := range []string{"thread_id", "query_id", "stage"} {
		if _, ok := rec[want]; !ok {
			t.Errorf("missing field %q in log line: %v", want, rec)
		}
	}
	if rec["msg"] != "hello" {
		t.Errorf("msg got %v want hello", rec["msg"])
	}
}

func TestParseLevel(t *testing.T) {
	cases := map[string]string{
		"debug": "DEBUG", "DEBUG": "DEBUG",
		"warn": "WARN", "warning": "WARN",
		"error": "ERROR",
		"":      "INFO", "info": "INFO",
		"unknown": "INFO",
	}
	for in, want := range cases {
		got := parseLevel(in).String()
		if got != want {
			t.Errorf("parseLevel(%q) = %q, want %q", in, got, want)
		}
	}
}
