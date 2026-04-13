import type { SchemaTable } from "@/api/types";

/**
 * Sanitize a name for use in Mermaid ER diagrams.
 * Removes characters that break Mermaid syntax.
 */
function sanitize(name: string): string {
  return name.replace(/[^a-zA-Z0-9_]/g, "_");
}

/**
 * Simplify a SQL data type for Mermaid display.
 * e.g. "NVARCHAR(100)" -> "nvarchar", "INTEGER" -> "int"
 */
function simplifyType(dataType: string): string {
  const base = dataType.split("(")[0].trim().toLowerCase();
  const map: Record<string, string> = {
    integer: "int",
    bigint: "bigint",
    smallint: "smallint",
    tinyint: "tinyint",
    nvarchar: "nvarchar",
    varchar: "varchar",
    nchar: "nchar",
    char: "char",
    text: "text",
    ntext: "ntext",
    datetime: "datetime",
    datetime2: "datetime2",
    date: "date",
    time: "time",
    bit: "bit",
    decimal: "decimal",
    numeric: "numeric",
    float: "float",
    real: "real",
    money: "money",
    uniqueidentifier: "uuid",
    blob: "blob",
    boolean: "bool",
  };
  return map[base] ?? base;
}

/**
 * Convert a schema array to a Mermaid ER diagram string.
 */
export function schemaToMermaid(tables: SchemaTable[]): string {
  const lines: string[] = ["erDiagram"];

  // Build a set of table names for relationship validation
  const tableNames = new Set(tables.map((t) => t.table_name));

  // Collect relationships
  const relationships: string[] = [];
  for (const table of tables) {
    for (const fk of table.foreign_keys ?? []) {
      if (!tableNames.has(fk.primary_key_table)) continue;
      // Skip self-referencing FKs — mermaid renders these as broken dangling lines
      if (fk.primary_key_table === table.table_name) continue;
      const from = sanitize(table.table_name);
      const to = sanitize(fk.primary_key_table);
      relationships.push(`    ${to} ||--o{ ${from} : "${sanitize(fk.foreign_key)}"`);
    }
  }

  // Deduplicate relationships
  const uniqueRelationships = [...new Set(relationships)];
  for (const rel of uniqueRelationships) {
    lines.push(rel);
  }

  // Build entities
  for (const table of tables) {
    const name = sanitize(table.table_name);
    const pk = table.metadata?.primary_key;
    const fkCols = new Set((table.foreign_keys ?? []).map((fk) => fk.foreign_key));

    lines.push(`    ${name} {`);
    for (const col of table.columns) {
      const type = simplifyType(col.data_type);
      let marker = "";
      if (col.column_name === pk) marker = " PK";
      else if (fkCols.has(col.column_name)) marker = " FK";
      lines.push(`        ${type} ${sanitize(col.column_name)}${marker}`);
    }
    lines.push("    }");
  }

  return lines.join("\n");
}
