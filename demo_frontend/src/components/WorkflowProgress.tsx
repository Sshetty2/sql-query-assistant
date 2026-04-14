import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronRight, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import type { StatusEvent, PromptContext } from "@/api/types";
import { PromptViewer } from "@/components/PromptViewer";

interface WorkflowProgressProps {
  steps: StatusEvent[];
  isStreaming: boolean;
}

// Friendly labels for workflow node names
const NODE_LABELS: Record<string, string> = {
  initialize_connection: "Connecting to database",
  analyze_schema: "Analyzing database schema",
  filter_schema: "Filtering relevant tables",
  infer_foreign_keys: "Inferring foreign keys",
  format_schema_markdown: "Formatting schema",
  pre_planner: "Creating query strategy",
  planner: "Generating query plan",
  plan_audit: "Auditing plan",
  check_clarification: "Checking for ambiguities",
  generate_query: "Generating SQL",
  execute_query: "Executing query",
  handle_tool_error: "Correcting error",
  handle_error: "Correcting error",
  refine_query: "Refining query",
  generate_modification_options: "Preparing options",
  generate_data_summary: "Summarizing data",
  generate_query_narrative: "Writing narrative",
  cleanup: "Finishing up",
};

// Nodes to hide (implementation details)
const HIDDEN_NODES = new Set([
  "initialize_connection",
  "format_schema_markdown",
  "check_clarification",
  "cleanup",
  "generate_modification_options",
  "generate_data_summary",
  "generate_query_narrative",
]);

function getNodeLabel(nodeName: string): string {
  return NODE_LABELS[nodeName] || nodeName.replace(/_/g, " ");
}

// ── Node-specific metadata renderers ──

function FilterSchemaMetadata({ meta }: { meta: Record<string, unknown> }) {
  const tables = (meta.selected_tables as string[]) || [];
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">
        Analyzed {meta.total_tables_in_db as number} tables &rarr; selected{" "}
        {meta.final_table_count as number}
      </p>
      {tables.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tables.map((t) => (
            <Badge key={t} variant="outline" className="text-[10px] px-1.5 py-0">
              {t}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function PrePlannerMetadata({ meta }: { meta: Record<string, unknown> }) {
  const preview = (meta.strategy_preview as string) || "";
  return (
    <div className="space-y-1">
      {Boolean(meta.has_feedback) && (
        <Badge variant="outline" className="text-[10px]">
          Feedback: {meta.feedback_type as string}
        </Badge>
      )}
      {preview && (
        <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-4">
          {preview}
        </p>
      )}
    </div>
  );
}

function PlannerMetadata({ meta }: { meta: Record<string, unknown> }) {
  const tables = (meta.tables as string[]) || [];
  return (
    <div className="space-y-1.5">
      {typeof meta.intent_summary === "string" && meta.intent_summary.length > 0 && (
        <p className="text-xs font-medium">{meta.intent_summary as string}</p>
      )}
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline" className="text-[10px]">
          {meta.table_count as number} tables
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {meta.join_count as number} joins
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {meta.filter_count as number} filters
        </Badge>
        {Boolean(meta.has_aggregation) && (
          <Badge variant="outline" className="text-[10px]">GROUP BY</Badge>
        )}
        {Boolean(meta.has_order_by) && (
          <Badge variant="outline" className="text-[10px]">ORDER BY</Badge>
        )}
        {meta.limit != null && (
          <Badge variant="outline" className="text-[10px]">
            LIMIT {meta.limit as number}
          </Badge>
        )}
      </div>
      {tables.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tables.map((t) => (
            <Badge key={t} variant="secondary" className="text-[10px] px-1.5 py-0">
              {t}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function PlanAuditMetadata({ meta }: { meta: Record<string, unknown> }) {
  const passed = meta.audit_passed as boolean;
  const issues = (meta.issues_preview as string[]) || [];
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Badge variant={passed ? "secondary" : "outline"} className="text-[10px]">
          {passed ? "Passed" : `${meta.issues_found} issues`}
        </Badge>
        {(meta.fixes_applied as number) > 0 && (
          <Badge variant="outline" className="text-[10px]">
            {meta.fixes_applied as number} auto-fixed
          </Badge>
        )}
      </div>
      {issues.length > 0 && (
        <ul className="text-[10px] text-muted-foreground list-disc pl-4 space-y-0.5">
          {issues.map((issue, i) => (
            <li key={i} className="line-clamp-1">{issue}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function GenerateQueryMetadata({ meta }: { meta: Record<string, unknown> }) {
  const preview = (meta.sql_preview as string) || "";
  return (
    <div className="space-y-1">
      {preview && (
        <pre className="text-[10px] text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
          {preview}
        </pre>
      )}
    </div>
  );
}

function ExecuteQueryMetadata({ meta }: { meta: Record<string, unknown> }) {
  const columns = (meta.columns as string[]) || [];
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="secondary" className="text-[10px]">
          {meta.row_count as number} rows
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {meta.column_count as number} columns
        </Badge>
        {Boolean(meta.limit_applied) && (
          <Badge variant="outline" className="text-[10px]">
            {meta.total_records_available as number} total available
          </Badge>
        )}
      </div>
      {columns.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {columns.map((c) => (
            <Badge key={c} variant="outline" className="text-[10px] px-1.5 py-0 font-mono">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function HandleErrorMetadata({ meta }: { meta: Record<string, unknown> }) {
  const preview = (meta.error_preview as string) || "";
  return (
    <div className="space-y-1">
      <Badge variant="destructive" className="text-[10px]">
        Attempt {meta.iteration as number}/{meta.max_iterations as number}
      </Badge>
      {preview && (
        <p className="text-[10px] text-muted-foreground line-clamp-2">{preview}</p>
      )}
    </div>
  );
}

function RefineQueryMetadata({ meta }: { meta: Record<string, unknown> }) {
  return (
    <Badge variant="outline" className="text-[10px]">
      Attempt {meta.iteration as number}/{meta.max_iterations as number}
    </Badge>
  );
}

function GenericMetadata({ meta }: { meta: Record<string, unknown> }) {
  const entries = Object.entries(meta).filter(
    ([, v]) => v != null && typeof v !== "object"
  );
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.slice(0, 6).map(([k, v]) => (
        <Badge key={k} variant="outline" className="text-[10px]">
          {k}: {String(v).slice(0, 40)}
        </Badge>
      ))}
    </div>
  );
}

// Map node names to their metadata renderers
const METADATA_RENDERERS: Record<
  string,
  React.ComponentType<{ meta: Record<string, unknown> }>
> = {
  filter_schema: FilterSchemaMetadata,
  pre_planner: PrePlannerMetadata,
  planner: PlannerMetadata,
  plan_audit: PlanAuditMetadata,
  generate_query: GenerateQueryMetadata,
  execute_query: ExecuteQueryMetadata,
  handle_tool_error: HandleErrorMetadata,
  handle_error: HandleErrorMetadata,
  refine_query: RefineQueryMetadata,
};

// ── Timeline step component ──

interface TimelineStepProps {
  step: StatusEvent;
  isLast: boolean;
}

function TimelineStep({ step, isLast }: TimelineStepProps) {
  const meta = step.node_metadata;
  const promptContext = meta?.prompt_context as PromptContext | undefined;
  // Consider metadata present if there are keys other than prompt_context
  const metaKeysWithoutPrompt = meta
    ? Object.keys(meta).filter((k) => k !== "prompt_context")
    : [];
  const hasMetadata = metaKeysWithoutPrompt.length > 0;
  const [expanded, setExpanded] = useState(hasMetadata);

  // Auto-expand when metadata arrives (step starts as "running" with no metadata,
  // then gets "completed" with metadata)
  useEffect(() => {
    if (hasMetadata) setExpanded(true);
  }, [hasMetadata]);

  const MetadataRenderer = METADATA_RENDERERS[step.node_name] || GenericMetadata;

  // Status dot styles
  const dotClass =
    step.node_status === "running"
      ? "bg-blue-500 animate-pulse"
      : step.node_status === "error"
        ? "bg-destructive"
        : "bg-green-500";

  const StatusIcon =
    step.node_status === "running"
      ? Loader2
      : step.node_status === "error"
        ? AlertCircle
        : CheckCircle2;

  const iconColor =
    step.node_status === "running"
      ? "text-blue-500"
      : step.node_status === "error"
        ? "text-destructive"
        : "text-green-600";

  return (
    <div className="relative flex gap-3">
      {/* Vertical line + dot */}
      <div className="flex flex-col items-center">
        <div className={`h-2.5 w-2.5 rounded-full mt-1 flex-shrink-0 ${dotClass}`} />
        {!isLast && <div className="w-px flex-1 bg-border min-h-4" />}
      </div>

      {/* Content */}
      <div className="flex-1 pb-3 min-w-0">
        {hasMetadata ? (
          <Collapsible open={expanded} onOpenChange={setExpanded}>
            <CollapsibleTrigger className="flex items-center gap-1.5 w-full text-left group">
              <StatusIcon className={`h-3.5 w-3.5 flex-shrink-0 ${iconColor} ${step.node_status === "running" ? "animate-spin" : ""}`} />
              <span className="text-sm font-medium flex-1">{getNodeLabel(step.node_name)}</span>
              {step.node_message && step.node_status === "running" && (
                <span className="text-xs text-muted-foreground mr-1">{step.node_message}</span>
              )}
              {promptContext && (
                <PromptViewer promptContext={promptContext} nodeName={getNodeLabel(step.node_name)} />
              )}
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-1.5 pl-5">
              <MetadataRenderer meta={meta!} />
            </CollapsibleContent>
          </Collapsible>
        ) : (
          <div className="flex items-center gap-1.5">
            <StatusIcon className={`h-3.5 w-3.5 flex-shrink-0 ${iconColor} ${step.node_status === "running" ? "animate-spin" : ""}`} />
            <span className="text-sm font-medium">{getNodeLabel(step.node_name)}</span>
            {step.node_message && step.node_status === "running" && (
              <span className="text-xs text-muted-foreground">{step.node_message}</span>
            )}
            {promptContext && (
              <PromptViewer promptContext={promptContext} nodeName={getNodeLabel(step.node_name)} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ──

export function WorkflowProgress({ steps, isStreaming }: WorkflowProgressProps) {
  const [isOpen, setIsOpen] = useState(true);

  // Deduplicate: show the latest status per node, filter hidden nodes
  const nodeMap = new Map<string, StatusEvent>();
  for (const step of steps) {
    if (step.node_name && !HIDDEN_NODES.has(step.node_name)) {
      // Merge metadata: keep the latest metadata from completed events
      const existing = nodeMap.get(step.node_name);
      if (existing && step.node_metadata) {
        nodeMap.set(step.node_name, { ...step });
      } else if (existing && !step.node_metadata && existing.node_metadata) {
        // Keep existing metadata if new event doesn't have it
        nodeMap.set(step.node_name, { ...step, node_metadata: existing.node_metadata });
      } else {
        nodeMap.set(step.node_name, step);
      }
    }
  }
  const visibleSteps = Array.from(nodeMap.values());

  const completedCount = visibleSteps.filter(
    (s) => s.node_status === "completed"
  ).length;
  const totalCount = visibleSteps.length;

  // Auto-collapse when streaming finishes
  const handleStreamEnd = useCallback(() => {
    setIsOpen(false);
  }, []);

  useEffect(() => {
    if (!isStreaming && visibleSteps.length > 0) {
      // Small delay for the user to see the final step complete
      const timer = setTimeout(handleStreamEnd, 600);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, visibleSteps.length, handleStreamEnd]);

  // Re-expand when a new stream starts
  useEffect(() => {
    if (isStreaming) setIsOpen(true);
  }, [isStreaming]);

  if (visibleSteps.length === 0) return null;

  return (
    <Card className="overflow-hidden">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="flex items-center w-full px-4 py-3 text-left hover:bg-muted/50 transition-colors">
          <div className="flex items-center gap-2 flex-1">
            {isStreaming ? (
              <Loader2 className="h-4 w-4 text-blue-500 animate-spin flex-shrink-0" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-green-600 flex-shrink-0" />
            )}
            <span className="text-sm font-medium">
              {isStreaming ? "Processing query..." : "Query workflow completed"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              {completedCount}/{totalCount}
            </Badge>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-1">
            {visibleSteps.map((step, i) => (
              <TimelineStep
                key={step.node_name}
                step={step}
                isLast={i === visibleSteps.length - 1}
              />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
