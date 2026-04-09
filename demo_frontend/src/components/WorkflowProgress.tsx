import { Badge } from "@/components/ui/badge";
import type { StatusEvent } from "@/api/types";

interface WorkflowProgressProps {
  steps: StatusEvent[];
}

// Friendly labels for workflow node names
const NODE_LABELS: Record<string, string> = {
  initialize_connection: "Connecting to database",
  analyze_schema: "Analyzing schema",
  filter_schema: "Filtering relevant tables",
  infer_foreign_keys: "Inferring foreign keys",
  format_schema_markdown: "Formatting schema",
  pre_planner: "Creating strategy",
  planner: "Generating query plan",
  plan_audit: "Auditing plan",
  check_clarification: "Checking for ambiguities",
  generate_query: "Generating SQL",
  execute_query: "Executing query",
  handle_error: "Handling error",
  refine_query: "Refining query",
  generate_modification_options: "Preparing options",
  cleanup: "Finishing up",
};

function getNodeLabel(nodeName: string): string {
  return NODE_LABELS[nodeName] || nodeName.replace(/_/g, " ");
}

function getStatusVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "running":
      return "default";
    case "completed":
      return "secondary";
    case "error":
      return "destructive";
    default:
      return "outline";
  }
}

export function WorkflowProgress({ steps }: WorkflowProgressProps) {
  if (steps.length === 0) return null;

  // Deduplicate: show the latest status per node
  const nodeMap = new Map<string, StatusEvent>();
  for (const step of steps) {
    if (step.node_name) {
      nodeMap.set(step.node_name, step);
    }
  }

  const uniqueSteps = Array.from(nodeMap.values());

  return (
    <div className="flex flex-wrap gap-2">
      {uniqueSteps.map((step) => (
        <Badge
          key={step.node_name}
          variant={getStatusVariant(step.node_status)}
          className="text-xs"
        >
          {step.node_status === "running" && (
            <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
          )}
          {getNodeLabel(step.node_name)}
        </Badge>
      ))}
    </div>
  );
}
