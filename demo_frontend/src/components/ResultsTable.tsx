import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ResultsTableProps {
  data: Record<string, unknown>[] | null;
  totalRecords?: number | null;
}

export function ResultsTable({ data, totalRecords }: ResultsTableProps) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No results returned.
        </CardContent>
      </Card>
    );
  }

  // Derive columns from the first non-null row. The backend type says the
  // array contains row objects, but reality (chat tool_result samples,
  // server crashes mid-stream, schema evolution) sometimes hands us a row
  // that's null/undefined. Object.keys(null) throws and crashes the UI —
  // crash recovery is more important than row-shape correctness here.
  const firstRow = data.find(
    (row): row is Record<string, unknown> => row != null && typeof row === "object",
  );
  if (!firstRow) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Result rows arrived in an unexpected shape (rows are null or non-object).
          The query may have returned no real data.
        </CardContent>
      </Card>
    );
  }
  // eslint-disable-next-line no-restricted-syntax -- firstRow narrowed to non-null object by the .find() type guard
  const columns = Object.keys(firstRow);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">
          Results
          <span className="ml-2 text-muted-foreground font-normal">
            {data.length} row{data.length !== 1 && "s"}
            {totalRecords != null && totalRecords > data.length && (
              <> of {totalRecords} total</>
            )}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((col) => (
                  <TableHead key={col} className="whitespace-nowrap">
                    {col}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, i) => {
                // Defend against rows that aren't object-shaped — same
                // class of bug as the firstRow guard above. Render an
                // explicit dash row so the user knows something arrived
                // even though it can't be displayed.
                const safeRow: Record<string, unknown> =
                  row != null && typeof row === "object" ? row : {};
                return (
                  <TableRow key={i} className="even:bg-muted/30">
                    {columns.map((col) => (
                      <TableCell key={col} className="whitespace-nowrap">
                        {safeRow[col] == null ? (
                          <span className="text-muted-foreground italic">null</span>
                        ) : (
                          String(safeRow[col])
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
