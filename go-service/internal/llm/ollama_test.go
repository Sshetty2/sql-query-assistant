package llm

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"
)

// TestOllama_Live talks to a real Ollama server if reachable AND the user
// explicitly opts in via `OLLAMA_TEST=true`. Both are required because
// cold-loading a model can consume 10+ GB of RAM and several CPU-minutes —
// not something we want a casual `go test ./...` run to trigger.
//
// To run:
//
//	OLLAMA_TEST=true OLLAMA_BASE_URL=http://localhost:11434 \
//	LOCAL_MODEL_PLANNING=llama3:8b go test ./internal/llm/... -run TestOllama_Live -v
func TestOllama_Live(t *testing.T) {
	loadRepoEnv(t)
	if testing.Short() {
		t.Skip("short mode")
	}
	if os.Getenv("OLLAMA_TEST") != "true" {
		t.Skip("set OLLAMA_TEST=true to run (cold model load uses ~10 GB RAM)")
	}
	base := os.Getenv("OLLAMA_BASE_URL")
	if base == "" {
		base = "http://localhost:11434"
	}
	// Quick reachability probe — skip cleanly when no Ollama is running.
	probe := &http.Client{Timeout: 1 * time.Second}
	resp, err := probe.Get(base + "/api/tags")
	if err != nil || resp.StatusCode >= 500 {
		t.Skipf("Ollama not reachable at %s; skipping", base)
	}
	defer resp.Body.Close()

	model := os.Getenv("LOCAL_MODEL_PLANNING")
	if model == "" {
		model = "llama3:8b"
	}

	// Verify the model is actually pulled — without this we get a hang while
	// Ollama tries to download it on first request, which dwarfs any test timeout.
	body, _ := io.ReadAll(resp.Body)
	var tags struct {
		Models []struct{ Name string } `json:"models"`
	}
	if err := json.Unmarshal(body, &tags); err == nil {
		found := false
		var available []string
		for _, m := range tags.Models {
			available = append(available, m.Name)
			if strings.HasPrefix(m.Name, model) || m.Name == model {
				found = true
				break
			}
		}
		if !found {
			t.Skipf("model %q not pulled; available: %v. Run `ollama pull %s` to enable this test", model, available, model)
		}
	}

	t.Setenv("USE_LOCAL_LLM", "true")
	c, err := New(model)
	if err != nil {
		t.Fatalf("new ollama client: %v", err)
	}

	// Cold-loading a fresh model can take 60+ seconds — first request loads
	// weights into VRAM. Subsequent calls are fast. 4 minutes is generous
	// enough to absorb the worst case while still failing if the server hangs.
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()

	out, err := c.Chat(ctx, []Message{
		{Role: RoleSystem, Content: "Reply with the single word: pong"},
		{Role: RoleUser, Content: "ping"},
	})
	if err != nil {
		t.Fatalf("chat: %v", err)
	}
	t.Logf("ollama replied: %q", out)
	if out == "" {
		t.Error("expected non-empty response from Ollama")
	}
}

func TestOllama_RoutesViaUseLocalLLM(t *testing.T) {
	// Verify that USE_LOCAL_LLM=true causes New() to return an ollamaClient
	// regardless of model name. We don't actually hit the network here.
	t.Setenv("USE_LOCAL_LLM", "true")
	c, err := New("anything-goes")
	if err != nil {
		t.Fatalf("expected ollamaClient construction to succeed: %v", err)
	}
	if _, ok := c.(*ollamaClient); !ok {
		t.Errorf("expected *ollamaClient, got %T", c)
	}
}
