import { type ReactElement } from "react";

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
  "CROSS", "ON", "AND", "OR", "NOT", "IN", "IS", "NULL", "AS", "ORDER",
  "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "DISTINCT", "TOP", "CASE",
  "WHEN", "THEN", "ELSE", "END", "UNION", "ALL", "INSERT", "INTO",
  "VALUES", "UPDATE", "SET", "DELETE", "CREATE", "ALTER", "DROP", "TABLE",
  "INDEX", "VIEW", "EXISTS", "BETWEEN", "LIKE", "ASC", "DESC", "WITH",
  "OVER", "PARTITION", "ROWS", "RANGE", "FULL", "NATURAL", "USING",
  "EXCEPT", "INTERSECT", "FETCH", "NEXT", "ONLY", "CAST", "COALESCE",
]);

const SQL_FUNCTIONS = new Set([
  "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "UPPER", "LOWER",
  "LENGTH", "LEN", "TRIM", "LTRIM", "RTRIM", "SUBSTRING", "CONCAT",
  "REPLACE", "GETDATE", "DATEPART", "DATEDIFF", "DATEADD", "CONVERT",
  "ISNULL", "NULLIF", "IIF", "ROW_NUMBER", "RANK", "DENSE_RANK",
  "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE", "STRING_AGG",
  "STUFF", "CHARINDEX", "PATINDEX", "FORMAT", "TRY_CAST", "TRY_CONVERT",
  "YEAR", "MONTH", "DAY",
]);

interface Token {
  type: "keyword" | "function" | "string" | "number" | "comment" | "plain";
  value: string;
}

function tokenize(sql: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < sql.length) {
    // Single-line comment
    if (sql[i] === "-" && sql[i + 1] === "-") {
      const end = sql.indexOf("\n", i);
      const value = end === -1 ? sql.slice(i) : sql.slice(i, end);
      tokens.push({ type: "comment", value });
      i += value.length;
      continue;
    }

    // Block comment
    if (sql[i] === "/" && sql[i + 1] === "*") {
      const end = sql.indexOf("*/", i + 2);
      const value = end === -1 ? sql.slice(i) : sql.slice(i, end + 2);
      tokens.push({ type: "comment", value });
      i += value.length;
      continue;
    }

    // String literal
    if (sql[i] === "'") {
      let j = i + 1;
      while (j < sql.length) {
        if (sql[j] === "'" && sql[j + 1] === "'") {
          j += 2; // escaped quote
        } else if (sql[j] === "'") {
          j++;
          break;
        } else {
          j++;
        }
      }
      tokens.push({ type: "string", value: sql.slice(i, j) });
      i = j;
      continue;
    }

    // Number
    if (/\d/.test(sql[i]) && (i === 0 || /[\s,=(+\-*/]/.test(sql[i - 1]))) {
      let j = i;
      while (j < sql.length && /[\d.]/.test(sql[j])) j++;
      tokens.push({ type: "number", value: sql.slice(i, j) });
      i = j;
      continue;
    }

    // Word (keyword, function, or identifier)
    if (/[a-zA-Z_]/.test(sql[i])) {
      let j = i;
      while (j < sql.length && /[a-zA-Z0-9_]/.test(sql[j])) j++;
      const word = sql.slice(i, j);
      const upper = word.toUpperCase();

      if (SQL_FUNCTIONS.has(upper)) {
        tokens.push({ type: "function", value: word });
      } else if (SQL_KEYWORDS.has(upper)) {
        tokens.push({ type: "keyword", value: word });
      } else {
        tokens.push({ type: "plain", value: word });
      }
      i = j;
      continue;
    }

    // Whitespace and other characters
    let j = i;
    while (
      j < sql.length &&
      !/[a-zA-Z_0-9']/.test(sql[j]) &&
      !(sql[j] === "-" && sql[j + 1] === "-") &&
      !(sql[j] === "/" && sql[j + 1] === "*")
    ) {
      j++;
    }
    if (j === i) j = i + 1;
    tokens.push({ type: "plain", value: sql.slice(i, j) });
    i = j;
  }

  return tokens;
}

const TOKEN_CLASSES: Record<Token["type"], string> = {
  keyword: "text-chart-2 font-semibold",
  function: "text-chart-3",
  string: "text-chart-1",
  number: "text-chart-5",
  comment: "text-muted-foreground italic",
  plain: "",
};

export function highlightSQL(sql: string): ReactElement[] {
  const tokens = tokenize(sql);
  return tokens.map((token, i) => {
    const cls = TOKEN_CLASSES[token.type];
    if (!cls) return <span key={i}>{token.value}</span>;
    return (
      <span key={i} className={cls}>
        {token.value}
      </span>
    );
  });
}
