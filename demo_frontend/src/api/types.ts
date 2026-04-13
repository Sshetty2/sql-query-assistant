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
  chat_session_id?: string;
  db_id?: string;
}

export interface DemoDatabase {
  id: string;
  name: string;
  description: string;
  file: string;
}

export interface SchemaTable {
  table_name: string;
  columns: { column_name: string; data_type: string; is_nullable: boolean }[];
  foreign_keys?: { foreign_key: string; primary_key_table: string; primary_key_column: string }[];
  metadata?: { primary_key?: string };
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
  node_metadata?: Record<string, unknown>;
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
  data_summary: DataSummary | null;
  query_narrative: string | null;
}

// Data summary types

export interface ColumnSummary {
  type: "numeric" | "text" | "datetime" | "boolean" | "null";
  null_count: number;
  distinct_count: number;
  min?: number | string | null;
  max?: number | string | null;
  avg?: number | null;
  median?: number | null;
  sum?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  avg_length?: number | null;
  top_values?: { value: string; count: number }[];
  range_days?: number | null;
}

export interface DataSummary {
  row_count: number;
  total_records_available: number | null;
  column_count: number;
  columns: Record<string, ColumnSummary>;
}

// Chat types

export interface ChatMessage {
  role: "user" | "assistant" | "tool_start" | "tool_result" | "tool_error" | "data_summary";
  content: string;
  resultId?: string; // Links to a stored QueryResult in localStorage
  failedQuery?: string; // The query that failed (for retry)
  dataSummary?: DataSummary; // Inline data summary stats (for data_summary and tool_result)
  query?: string; // SQL query text (for data_summary messages)
}

export interface ChatRequest {
  thread_id: string;
  query_id: string;
  message: string;
  session_id?: string;
}

export interface ChatTokenEvent {
  content: string;
}

export interface ChatToolStartEvent {
  tool: string;
  input: { query: string };
}

export interface ChatToolErrorEvent {
  detail: string;
  query: string;
}

export interface ChatCompleteEvent {
  content: string;
  suggest_new_query: boolean;
  suggested_query: string | null;
  tool_calls_remaining: number;
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
