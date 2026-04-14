import { useEffect, useRef, useState, useCallback } from "react";
import DOMPurify from "dompurify";
import mermaid from "mermaid";
import svgPanZoom from "svg-pan-zoom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChevronDown, ChevronRight, ZoomIn, ZoomOut, Maximize } from "lucide-react";
import { schemaToMermaid } from "@/utils/schemaToMermaid";
import type { SchemaTable } from "@/api/types";

interface SchemaERDProps {
  schema: SchemaTable[];
  dbName: string;
}

let mermaidInitialized = false;
let renderCounter = 0;

function ensureMermaidInit() {
  if (mermaidInitialized) return;
  mermaidInitialized = true;
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      darkMode: true,
      background: "transparent",
      primaryColor: "#2d3352",
      primaryTextColor: "#c5c9d6",
      primaryBorderColor: "#424868",
      lineColor: "#5b82d1",
      secondaryColor: "#252a40",
      tertiaryColor: "#1e2235",
      fontFamily: "'Geist Variable', sans-serif",
      fontSize: "16px",
    },
    er: {
      useMaxWidth: false,
      layoutDirection: "LR",
    },
  });
}

interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

function ZoomControls({ onZoomIn, onZoomOut, onReset }: ZoomControlsProps) {
  return (
    <div className="absolute top-2 right-2 z-10 flex gap-1">
      <button
        onClick={onZoomIn}
        className="p-1.5 rounded-md bg-secondary hover:bg-accent text-foreground transition-colors"
        title="Zoom in"
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        onClick={onZoomOut}
        className="p-1.5 rounded-md bg-secondary hover:bg-accent text-foreground transition-colors"
        title="Zoom out"
      >
        <ZoomOut className="h-4 w-4" />
      </button>
      <button
        onClick={onReset}
        className="p-1.5 rounded-md bg-secondary hover:bg-accent text-foreground transition-colors"
        title="Fit to view"
      >
        <Maximize className="h-4 w-4" />
      </button>
    </div>
  );
}

export function SchemaERD({ schema, dbName }: SchemaERDProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const panZoomRef = useRef<SvgPanZoom.Instance | null>(null);
  const [open, setOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleZoomIn = useCallback(() => panZoomRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => panZoomRef.current?.zoomOut(), []);
  const handleReset = useCallback(() => {
    panZoomRef.current?.fit();
    panZoomRef.current?.center();
  }, []);

  // Render mermaid SVG and attach svg-pan-zoom
  useEffect(() => {
    if (!open || !containerRef.current || schema.length === 0) return;

    ensureMermaidInit();

    const definition = schemaToMermaid(schema);
    renderCounter += 1;
    const id = `erd_${renderCounter}`;

    const container = containerRef.current;

    // Destroy previous instance before re-rendering
    panZoomRef.current?.destroy();
    panZoomRef.current = null;
    container.innerHTML = "";

    let cancelled = false;

    mermaid
      .render(id, definition)
      .then(({ svg }) => {
        if (cancelled || !container) return;

        container.innerHTML = DOMPurify.sanitize(svg, {
          USE_PROFILES: { svg: true, svgFilters: true },
          ADD_TAGS: ["foreignObject"],
        });
        setError(null);

        const svgEl = container.querySelector("svg");
        if (!svgEl) return;

        // Let SVG fill the container so svg-pan-zoom can manage the viewport
        svgEl.style.width = "100%";
        svgEl.style.height = "100%";

        panZoomRef.current = svgPanZoom(svgEl, {
          zoomScaleSensitivity: 0.5,
          minZoom: 0.8,
          maxZoom: 5,
          fit: true,
          center: true,
          controlIconsEnabled: false,
          dblClickZoomEnabled: false,
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err));
        }
      });

    return () => {
      cancelled = true;
      panZoomRef.current?.destroy();
      panZoomRef.current = null;
      const tempEl = document.getElementById(id);
      if (tempEl) tempEl.remove();
    };
  }, [schema, open]);

  // Handle window resize — re-fit the diagram
  useEffect(() => {
    const handleResize = () => {
      panZoomRef.current?.resize();
      panZoomRef.current?.fit();
      panZoomRef.current?.center();
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const visibleTables = schema.filter(
    (t) => !t.table_name.startsWith("sqlite_")
  );

  return (
    <Card>
      <CardHeader
        className="pb-3 cursor-pointer select-none"
        onClick={() => setOpen((prev) => !prev)}
      >
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {dbName} Schema
          <span className="text-muted-foreground font-normal">
            ({visibleTables.length} tables)
          </span>
        </CardTitle>
      </CardHeader>
      {open && (
        <CardContent className="pt-0">
          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : (
            <div
              className="relative rounded-md border border-border overflow-hidden"
              style={{
                height: 400,
                backgroundImage: "radial-gradient(circle, oklch(0.40 0.015 260) 1px, transparent 1px)",
                backgroundSize: "20px 20px",
              }}
            >
              <ZoomControls
                onZoomIn={handleZoomIn}
                onZoomOut={handleZoomOut}
                onReset={handleReset}
              />
              <div
                ref={containerRef}
                style={{ width: "100%", height: "100%" }}
              />
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
