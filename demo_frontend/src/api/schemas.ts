// Runtime schemas for SSE payloads. Mirrors the most-rendered fields of
// `types.ts` — not every field, just the ones whose shape would crash a
// render if violated.
//
// Used in `validateQueryResult` (called from `client.ts` at the `complete`
// event boundary). In production we want to be permissive: log a warning,
// don't throw — a payload-shape glitch shouldn't break the user's session.
//
// Why we don't validate every nested field:
// - Full QueryResult has 25+ keys; validating each one would couple this
//   schema tightly to backend evolution and force an update for every
//   wire-format change that doesn't actually break the UI.
// - The render boundaries we care about are: rows array, data_summary,
//   modification_options, planner_output. A bad shape in any of these
//   would crash ResultsTable / ChatPanel / WorkflowProgress.
// - Other fields (correction_history, refinement_history, etc.) are
//   either string arrays or only ever inspected via optional chaining,
//   so a wrong shape would degrade gracefully.

import { z } from "zod";

// A single row from a query result. Must be a non-null object — that's the
// invariant ResultsTable.tsx depends on. Inner values can be anything.
const RowSchema = z.record(z.string(), z.unknown());

// Per-column statistics in a DataSummary. The Type field is the most
// load-bearing — ChatPanel branches on it to render different stat formats.
const ColumnSummarySchema = z.object({
  type: z.enum(["numeric", "text", "datetime", "boolean", "null"]),
  null_count: z.number(),
  distinct_count: z.number(),
}).passthrough(); // allow extra fields without complaint

const DataSummarySchema = z.object({
  row_count: z.number(),
  total_records_available: z.number().nullable(),
  column_count: z.number(),
  // The crash that triggered FRONTEND_HARDENING.md was on this shape.
  // Strict here: must be an object map, not null/undefined.
  columns: z.record(z.string(), ColumnSummarySchema),
}).passthrough();

const ModificationOptionsSchema = z.object({
  tables: z.record(z.string(), z.unknown()),
  sortable_columns: z.array(z.unknown()),
  current_order_by: z.array(z.unknown()).nullable(),
  current_limit: z.number().nullable(),
}).passthrough();

// QueryResult — the SSE `complete` event payload. We validate just the
// shape-critical bits and let `passthrough()` carry everything else.
export const QueryResultSchema = z.object({
  query: z.string(),
  // result MUST be either null or an array of objects (no naked nulls in the
  // array). The array-of-null case is what crashed ResultsTable.
  result: z.array(RowSchema).nullable(),
  thread_id: z.string().nullable(),
  query_id: z.string().nullable(),
  data_summary: DataSummarySchema.nullable().optional(),
  modification_options: ModificationOptionsSchema.nullable().optional(),
}).passthrough();

/**
 * Validate a QueryResult-shaped payload at the SSE boundary.
 *
 * Returns the parsed value if valid (semantically identical to the input).
 * On validation failure: logs a console warning with the zod error tree,
 * returns the original raw value unmodified, and lets the render layer
 * deal with it. The render layer's defensive guards (FRONTEND_HARDENING.md)
 * are still in place — this is just earlier visibility, not a hard gate.
 *
 * Only runs validation in dev mode (`import.meta.env.DEV`) so production
 * users don't pay the parse cost. The fallback is to return the raw value
 * unchanged so the rendering pipeline behaves identically with or without
 * validation.
 */
export function validateQueryResult(raw: unknown): unknown {
  if (!import.meta.env.DEV) return raw;

  const parsed = QueryResultSchema.safeParse(raw);
  if (!parsed.success) {
    // eslint-disable-next-line no-console
    console.warn(
      "[schema] QueryResult payload doesn't match expected shape — render guards will absorb this but the backend (or wire format) likely needs a fix:",
      parsed.error.format(),
    );
    return raw;
  }
  return parsed.data;
}
