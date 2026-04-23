// Package vector provides a tiny in-memory vector store. The Python service
// uses Chroma's in-process client to store ~30 table embeddings per query;
// for that scale a hand-rolled cosine-similarity scan is faster, has zero
// external dependencies, and is deterministic across runs.
package vector

import (
	"errors"
	"math"
	"sort"
)

// Doc is one indexed document — typically a table summary in our use case.
type Doc[M any] struct {
	Text     string
	Metadata M
}

// Store holds a slice of (doc, embedding) pairs and supports top-k cosine search.
type Store[M any] struct {
	docs    []Doc[M]
	vectors [][]float32
}

func NewStore[M any]() *Store[M] {
	return &Store[M]{}
}

// Add appends a document and its embedding. Embeddings should be the same
// dimensionality across all documents and queries; we don't enforce it because
// the OpenAI embedding endpoint always returns vectors of a fixed model size.
func (s *Store[M]) Add(doc Doc[M], embedding []float32) {
	s.docs = append(s.docs, doc)
	s.vectors = append(s.vectors, embedding)
}

// Result wraps a matched document with its similarity score.
type Result[M any] struct {
	Doc   Doc[M]
	Score float32
}

// Search returns the top-k documents by cosine similarity. Order is descending
// by score; ties broken by original insertion order (stable sort).
func (s *Store[M]) Search(query []float32, k int) ([]Result[M], error) {
	if len(s.vectors) == 0 {
		return nil, errors.New("vector store is empty")
	}
	if k <= 0 {
		return nil, errors.New("k must be positive")
	}

	scores := make([]Result[M], len(s.vectors))
	for i, v := range s.vectors {
		scores[i] = Result[M]{Doc: s.docs[i], Score: cosine(query, v)}
	}
	sort.SliceStable(scores, func(i, j int) bool {
		return scores[i].Score > scores[j].Score
	})
	if k > len(scores) {
		k = len(scores)
	}
	return scores[:k], nil
}

// Len reports how many docs are indexed.
func (s *Store[M]) Len() int { return len(s.docs) }

// cosine computes cosine similarity. Returns 0 for any zero-norm input
// rather than NaN, so empty embeddings don't poison the ranking.
func cosine(a, b []float32) float32 {
	if len(a) != len(b) || len(a) == 0 {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		af, bf := float64(a[i]), float64(b[i])
		dot += af * bf
		na += af * af
		nb += bf * bf
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return float32(dot / (math.Sqrt(na) * math.Sqrt(nb)))
}
