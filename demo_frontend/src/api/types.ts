// API request and response types matching the FastAPI server

export type SortOrder = "Default" | "Ascending" | "Descending";
export type TimeFilter =
  | "All Time"
  | "Last 24 Hours"
  | "Last 7 Days"
  | "Last 30 Days"
  | "Last Year";

export interface QueryRequest {
  prompt: string;
  sort_order?: SortOrder;
  result_limit?: number;
  time_filter?: TimeFilter;
}

export interface PatchRequest {
  thread_id: string;
  user_question: string;
  patch_operation: Record<string, unknown>;
  executed_plan: Record<string, unknown>;
  filtered_schema: Record<string, unknown>[];
}

export interface StatusEvent {
  type: "status";
  node_name: string;
  node_status: "running" | "completed" | "error";
  node_message?: string;
  node_logs?: string;
  log_level?: string;
}

export interface QueryResult {
  messages: string[];
  user_question: string;
  query: string;
  result: Record<string, unknown>[] | null;
  sort_order: string;
  result_limit: number;
  time_filter: string;
  last_step: string;
  error_iteration: number;
  refinement_iteration: number;
  correction_history: Record<string, unknown>[];
  refinement_history: Record<string, unknown>[];
  last_attempt_time: string | null;
  tables_used: string[];
  thread_id: string | null;
  query_id: string | null;
  planner_output: Record<string, unknown> | null;
  needs_clarification: boolean;
  clarification_suggestions: string[];
  modification_options: ModificationOptions | null;
  executed_plan: Record<string, unknown> | null;
  filtered_schema: Record<string, unknown>[] | null;
  total_records_available: number | null;
}

export interface ModificationOptions {
  tables: Record<
    string,
    {
      columns: { name: string; selected: boolean }[];
    }
  >;
  sortable_columns: { table: string; column: string }[];
  current_order_by: { table: string; column: string; direction: string }[] | null;
  current_limit: number | null;
}
