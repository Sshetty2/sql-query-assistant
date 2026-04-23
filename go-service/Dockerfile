# syntax=docker/dockerfile:1.7
#
# Multi-stage build for go-service. Produces a ~30 MB distroless image.
#
# Build:   docker build -t sql-go-service .
# Run:     docker run --rm -p 8001:8001 \
#            -e USE_TEST_DB=true \
#            -e OPENAI_API_KEY=$OPENAI_API_KEY \
#            -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
#            -v $(pwd)/databases:/app/databases:ro \
#            sql-go-service

# ---------------------------------------------------------------------------
# Stage 1: build
# ---------------------------------------------------------------------------
FROM golang:1.25-alpine AS builder

WORKDIR /src

# Cache module downloads in a separate layer.
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# CGO_ENABLED=0 keeps the binary fully static so it runs in distroless/static.
# Pure-Go modernc.org/sqlite + microsoft/go-mssqldb both work without CGO.
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/sql-go-service \
    ./cmd/server

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
# distroless/static is ~2 MB and contains nothing but the kernel ABI surface
# Go binaries need. No shell, no package manager — minimal attack surface.
FROM gcr.io/distroless/static-debian12:nonroot

WORKDIR /app

# Copy the binary and the demo database registry. Demo databases themselves
# are bind-mounted at runtime so the image stays small and rebuilds are fast.
COPY --from=builder /out/sql-go-service /app/sql-go-service

USER nonroot:nonroot
EXPOSE 8001

ENTRYPOINT ["/app/sql-go-service"]
