import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertCircle, RotateCw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  /** Friendly label shown in the fallback UI ("Results", "Chat panel", etc.). */
  section: string;
  /**
   * `subtle` is for inline/section boundaries — small inline card.
   * `page` is for the top-level boundary — full-page takeover with a refresh button.
   */
  variant?: "subtle" | "page";
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

// Module-scope dedupe set so the same crash from a re-rendering component
// doesn't spam the backend with identical reports during a single page
// session. Cleared by reload (the natural recovery action). Key shape:
// `<section>::<error.message>` — different sections get separate entries
// even if the message is the same, since they're different bugs.
const reportedErrors = new Set<string>();

/**
 * Fire a render-error report to the backend. Best-effort — failures here
 * must NOT throw, or the boundary itself crashes. Order of preference:
 *   1. navigator.sendBeacon (most reliable for "send before unload")
 *   2. fetch with keepalive (works in modern browsers, survives unload)
 *   3. silently no-op (we don't want to block the UI on a logging call)
 *
 * Endpoint matches both Python (server.py) and Go (go-service) backends.
 * Same `/log/render-error` path on both, same JSON body shape.
 */
function reportRenderError(payload: Record<string, unknown>) {
  try {
    const body = JSON.stringify(payload);
    const url = "/api/log/render-error";

    // sendBeacon is fire-and-forget and survives page unload, which matters
    // because uncaught errors can race with the user closing the tab.
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      // sendBeacon returns false if it couldn't queue the request (e.g.
      // exceeds browser's per-origin quota); fall through to fetch in that case.
      if (navigator.sendBeacon(url, blob)) {
        return;
      }
    }

    // keepalive: true lets the request continue past the page lifecycle
    // (browser-supported but capped at ~64 KB; our payload is well under).
    if (typeof fetch === "function") {
      void fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      }).catch(() => {
        // Swallow — telemetry mustn't crash the boundary.
      });
    }
  } catch {
    // Final guard: any synchronous throw from the helpers above (Blob ctor,
    // JSON.stringify on a non-serializable cycle, etc.) is silently dropped.
  }
}

/**
 * Catches render errors in the wrapped subtree so a crash in one component
 * doesn't unmount the whole app. Two variants:
 *
 *   - `page`: full-page takeover, used at the App root. User sees a
 *     friendly message + a button to reload.
 *   - `subtle` (default): a small inline card, used per-section so a bug
 *     in ResultsTable doesn't take down the chat panel and vice versa.
 *
 * Resetting: bumping the `key` prop on this component forces React to
 * remount the boundary AND its children, clearing the error. The retry
 * button below uses a state-based reset that keeps siblings mounted.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface to the console with section context so DevTools shows the
    // boundary that caught it. Stack-trace is in `error.stack`; React's
    // component stack is in info.componentStack.
    // eslint-disable-next-line no-console
    console.error(
      `[ErrorBoundary:${this.props.section}] render crashed`,
      error,
      info.componentStack,
    );

    // Telemetry: ping /log/render-error so production crashes get reported
    // even when no one's watching DevTools. Deduped per section+message so
    // a re-rendering broken component doesn't flood the backend.
    const key = `${this.props.section}::${error.message}`;
    if (reportedErrors.has(key)) return;
    reportedErrors.add(key);

    reportRenderError({
      section: this.props.section,
      error_message: error.message || "(no message)",
      // Cap stack/componentStack so we never approach the backend's 16 KB cap.
      // The backend truncates again at 1500 chars per field for log readability.
      error_stack: (error.stack || "").slice(0, 4000),
      component_stack: (info.componentStack || "").slice(0, 4000),
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "",
      url: typeof window !== "undefined" ? window.location.href : "",
    });
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.variant === "page") {
      return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-background">
          <Card className="max-w-lg border-destructive">
            <CardContent className="py-8 space-y-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-destructive flex-shrink-0 mt-0.5" />
                <div className="space-y-2 min-w-0">
                  <h2 className="text-lg font-semibold">Something went wrong</h2>
                  <p className="text-sm text-muted-foreground">
                    The {this.props.section} crashed unexpectedly. Reloading the
                    page should recover. If this keeps happening, copy the error
                    below and share it with the team.
                  </p>
                  <pre className="text-xs bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-words font-mono">
                    {error.message}
                  </pre>
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={this.reset}>
                  Try again
                </Button>
                <Button size="sm" onClick={() => window.location.reload()}>
                  <RotateCw className="h-3.5 w-3.5 mr-1.5" />
                  Reload page
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    // `subtle` — fits inside the section's normal layout.
    return (
      <Card className="border-destructive">
        <CardContent className="py-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
            <div className="space-y-1.5 min-w-0 flex-1">
              <p className="text-sm font-medium">{this.props.section} crashed</p>
              <p className="text-xs text-muted-foreground break-words">
                {error.message}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={this.reset}
                className="h-7 text-xs"
              >
                Retry this section
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }
}
