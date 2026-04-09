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

  const columns = Object.keys(data[0]);

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
              {data.map((row, i) => (
                <TableRow key={i}>
                  {columns.map((col) => (
                    <TableCell key={col} className="whitespace-nowrap">
                      {row[col] == null ? (
                        <span className="text-muted-foreground italic">null</span>
                      ) : (
                        String(row[col])
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
