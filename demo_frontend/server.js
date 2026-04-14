import crypto from "crypto";
import express from "express";
import rateLimit from "express-rate-limit";
import { createProxyMiddleware } from "http-proxy-middleware";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

// Suppress noisy DEP0060 from transitive proxy dependency on newer Node versions.
const originalEmitWarning = process.emitWarning.bind(process);
process.emitWarning = (warning, ...args) => {
  const warningCode = args[1] ?? warning?.code;
  if (warningCode === "DEP0060") return;
  return originalEmitWarning(warning, ...args);
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = process.env.PORT || 8080;
const API_URL = process.env.API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// CSRF token management
// ---------------------------------------------------------------------------

// In-memory token store with expiry (tokens valid for 24 hours)
const TOKEN_TTL_MS = 24 * 60 * 60 * 1000;
const csrfTokens = new Map();

function generateCsrfToken() {
  const token = crypto.randomBytes(32).toString("hex");
  csrfTokens.set(token, Date.now() + TOKEN_TTL_MS);
  return token;
}

function isValidCsrfToken(token) {
  if (!token || !csrfTokens.has(token)) return false;
  const expiry = csrfTokens.get(token);
  if (Date.now() > expiry) {
    csrfTokens.delete(token);
    return false;
  }
  return true;
}

// Periodically clean expired tokens (every 10 minutes)
setInterval(() => {
  const now = Date.now();
  for (const [token, expiry] of csrfTokens) {
    if (now > expiry) csrfTokens.delete(token);
  }
}, 10 * 60 * 1000);

// ---------------------------------------------------------------------------
// Rate limiting — per IP
// ---------------------------------------------------------------------------

const apiLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute window
  max: 20,             // max 20 API requests per minute per IP
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests, please try again later." },
});

// ---------------------------------------------------------------------------
// API proxy with CSRF validation
// ---------------------------------------------------------------------------

// CSRF validation middleware for /api routes
function csrfValidation(req, res, next) {
  const token = req.headers["x-csrf-token"];
  if (!isValidCsrfToken(token)) {
    return res.status(403).json({ error: "Invalid or missing CSRF token." });
  }
  next();
}

// Apply rate limiting and CSRF validation to all /api routes
app.use("/api", apiLimiter, csrfValidation);

// Proxy /api/* to the backend API (strips /api prefix)
app.use(
  "/api",
  createProxyMiddleware({
    target: API_URL,
    changeOrigin: true,
    pathRewrite: { "^/api": "" },
    // SSE streams are long-lived; default ~120s timeouts kill them prematurely
    timeout: 600000,       // 10 min — outgoing proxy request timeout (ms)
    proxyTimeout: 600000,  // 10 min — incoming proxy response timeout (ms)
    // SSE: disable buffering so events stream through immediately
    onProxyReq: (proxyReq) => {
      proxyReq.removeHeader("x-csrf-token");
      proxyReq.setHeader("X-Accel-Buffering", "no");
    },
    onProxyRes: (proxyRes) => {
      // Ensure no buffering/compression breaks SSE
      if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
        proxyRes.headers["cache-control"] = "no-cache";
        proxyRes.headers["connection"] = "keep-alive";
      }
    },
  })
);

// ---------------------------------------------------------------------------
// Static file serving with CSRF token injection
// ---------------------------------------------------------------------------

// Read the built index.html once at startup
const indexHtmlPath = path.join(__dirname, "dist", "index.html");
const indexHtmlTemplate = fs.readFileSync(indexHtmlPath, "utf-8");

// Serve static assets (JS, CSS, fonts, images) directly
app.use(express.static(path.join(__dirname, "dist"), {
  index: false, // Don't serve index.html for "/" — we handle that below
}));

// SPA fallback — inject a fresh CSRF token into every page load
app.get("/{*splat}", (_req, res) => {
  const token = generateCsrfToken();
  // Inject the token as a script tag before </head>
  const html = indexHtmlTemplate.replace(
    "</head>",
    `<script>window.__CSRF_TOKEN__="${token}";</script>\n  </head>`
  );
  res.setHeader("Content-Type", "text/html");
  res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  res.send(html);
});

app.listen(PORT, () => {
  console.log(`Frontend server listening on port ${PORT}`);
  console.log(`Proxying /api/* to ${API_URL}`);
});
