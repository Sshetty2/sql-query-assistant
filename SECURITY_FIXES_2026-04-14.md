# Security Fixes — SQL Query Assistant

**Date**: 2026-04-14
**Companion to**: `SECURITY_REVIEW_2026-04-14.md`

---

## Summary

Addressed **15 of 30** findings from the security review (all Critical, all High, 7 Medium, 1 Low). The remaining findings are either accepted risks, require larger architectural changes, or have negligible practical impact.

| Severity | Total | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 1 | 1 | 0 |
| High | 6 | 6 | 0 |
| Medium | 12 | 7 | 5 |
| Low | 8 | 1 | 7 |
| Info | 3 | 0 | 3 |

---

## Critical Fixes

### C-1. Unsanitized Markdown Rendering (XSS) — FIXED

**Files**: `demo_frontend/src/components/ChatPanel.tsx`, `demo_frontend/package.json`

Added `rehype-sanitize` plugin to both `<Markdown>` render sites (historical messages and streaming content). Any raw HTML in LLM responses is now stripped before rendering.

```tsx
import rehypeSanitize from "rehype-sanitize";
<Markdown rehypePlugins={[rehypeSanitize]}>{content}</Markdown>
```

---

## High Fixes

### H-1. Error Messages Leak Internal Details — FIXED

**File**: `server.py` (4 locations)

Replaced `str(e)` in all client-facing error responses with generic messages. The real exception is still logged server-side via `logger.error(..., exc_info=True)`.

| Endpoint | Client Message |
|----------|---------------|
| `POST /query` | "An internal error occurred. Please try again." |
| `POST /query/stream` | "Query failed. Please try rephrasing your question." |
| `POST /query/patch` | "Patch failed. Please try again." |
| `POST /query/chat` | "Chat request failed. Please try again." |

### H-2. Unbounded Session Registry (Memory Exhaustion) — FIXED

**File**: `server.py`

Added TTL-based eviction (10 minutes) and a max-size cap (200 sessions) to the `_active_sessions` registry. Stale entries are cleaned on every `register_session()` call. Registry values changed from bare `threading.Event` to `(Event, timestamp)` tuples.

### H-3. innerHTML SVG Injection in Schema ERD — FIXED

**Files**: `demo_frontend/src/components/SchemaERD.tsx`, `demo_frontend/package.json`

Added `DOMPurify.sanitize()` before assigning Mermaid SVG output to `container.innerHTML`.

```tsx
import DOMPurify from "dompurify";
container.innerHTML = DOMPurify.sanitize(svg);
```

### H-4. Path Traversal via Database Registry — FIXED

**File**: `database/connection.py`

Added `os.path.realpath()` validation in `get_demo_db_path()` to ensure the resolved database path stays within the `databases/` directory.

```python
if not os.path.realpath(db_path).startswith(os.path.realpath(_databases_dir)):
    raise ValueError(f"Invalid database path for {db_id}")
```

### H-5. CSRF Token Validation Not Timing-Safe — FIXED

**File**: `demo_frontend/server.js`

Replaced `Map.has()` lookup with a `crypto.timingSafeEqual()` loop over all stored tokens. Trades O(1) for O(n) iteration, acceptable given the small token set (< 100 entries with 2-hour TTL).

### H-6. Vulnerable Dependency: follow-redirects — FIXED

**File**: `demo_frontend/package-lock.json`

`npm audit fix` upgraded `follow-redirects` past the header-leak vulnerability. `npm audit` now reports 0 vulnerabilities.

---

## Medium Fixes

### M-2. Rate Limiter Bypassable via X-Forwarded-For Spoofing — FIXED

**File**: `demo_frontend/server.js`

Added `app.set("trust proxy", 1)` so Express uses Railway's real client IP instead of trusting arbitrary `X-Forwarded-For` values.

### M-3. Missing Security Headers — FIXED

**File**: `demo_frontend/server.js`

Added `helmet` middleware with a CSP policy tailored for the app (allows inline scripts for CSRF injection, unsafe-eval for mermaid/katex).

Headers now set: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Content-Security-Policy`.

### M-4. No Request Body Size Limit — FIXED

**File**: `demo_frontend/server.js`

Added `express.json({ limit: "1mb" })` before the proxy middleware.

### M-6. Thread Safety Issue in Chat Session Management — FIXED

**File**: `agent/chat_agent.py`

Added `threading.Lock` (`_chat_lock`) protecting all reads and writes to `_chat_sessions` and `_tool_call_counts` dictionaries (6 access sites).

### M-8. No Input Length Validation on QueryRequest — FIXED

**File**: `server.py`

Added `max_length=10000` to the `QueryRequest.prompt` Pydantic field. Requests exceeding this are rejected with a 422 validation error.

### M-9. X-Page-Session Header Not Validated — FIXED

**File**: `server.py`

Added `_validate_page_session()` helper that only accepts 64-character lowercase hex strings (matching `crypto.randomBytes(32).toString("hex")`). Invalid headers are treated as absent.

### M-12. 24-Hour CSRF Token TTL — FIXED

**File**: `demo_frontend/server.js`

Reduced `TOKEN_TTL_MS` from 24 hours to 2 hours.

---

## Low Fixes

### L-1. CSRF Token Exposed in `window.__CSRF_TOKEN__` — FIXED

**File**: `demo_frontend/server.js`

Changed from `window.__CSRF_TOKEN__ = "..."` to `Object.defineProperty` with `enumerable: false`, `configurable: false`, `writable: false`. The token is still accessible by name but no longer shows up in `Object.keys(window)` or casual enumeration.

---

## Remaining Findings (Not Addressed)

### Deferred — Requires Larger Changes

| Finding | Reason |
|---------|--------|
| **M-1** No backend rate limiting | Needs SlowAPI dependency + per-endpoint tuning |
| **M-5** Unbounded `fetchall()` | Needs `fetchmany()` refactor + testing against real databases |
| **M-7** LLM prompt injection | No quick mitigation — needs research into detection heuristics |
| **M-10** Credentials in ODBC string | Needs logging infrastructure changes |

### Accepted Risk

| Finding | Reason |
|---------|--------|
| **M-11** No backend auth | By design — backend is private (Railway internal networking only) |

### Low / Informational — Not Actioned

| Finding | Reason |
|---------|--------|
| **L-2** localStorage stores results | Acceptable for demo; no sensitive data in demo DBs |
| **L-3** SSE parser trusts event types | TypeScript casts; would need runtime validation library |
| **L-4** thread_states.json no validation | Internal file; corruption is self-healing (new thread created) |
| **L-5** Debug file writes | Filenames are hardcoded (safe) |
| **L-6** `default=str` serialization | Removing would risk breaking SSE events |
| **L-7** Predictable cleanup interval | Negligible information leak |
| **L-8** No CSP meta tag | Now handled via `helmet` response headers (M-3 fix) |
| **I-1** No CORS | Intentional (private backend) |
| **I-2** 10-min proxy timeout | Required for long-running SSE streams |
| **I-3** SQLGlot AST generation | Already mitigates SQL injection |

---

## Files Modified

| File | Changes |
|------|---------|
| `server.py` | Generic error messages (4 sites), session registry TTL + max-size, prompt max_length, page-session validation |
| `demo_frontend/server.js` | helmet, trust proxy, body size limit, timing-safe CSRF, reduced TTL, non-enumerable token |
| `demo_frontend/src/components/ChatPanel.tsx` | rehype-sanitize on Markdown |
| `demo_frontend/src/components/SchemaERD.tsx` | DOMPurify on Mermaid SVG |
| `database/connection.py` | Path traversal validation |
| `agent/chat_agent.py` | threading.Lock on shared dicts |
| `demo_frontend/package.json` | Added rehype-sanitize, dompurify, helmet |
| `demo_frontend/package-lock.json` | Updated follow-redirects, added new deps |
| `tests/unit/test_workflow_cancellation.py` | Updated for (event, timestamp) tuple format |

## Verification

- **Frontend build**: `npm run build` passes (TypeScript + Vite)
- **Python tests**: 441 passed, 0 failed
- **npm audit**: 0 vulnerabilities
