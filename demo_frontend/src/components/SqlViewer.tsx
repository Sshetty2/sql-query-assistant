import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { highlightSQL } from "@/utils/sqlHighlight";

interface SqlViewerProps {
  sql: string;
}

export function SqlViewer({ sql }: SqlViewerProps) {
  if (!sql) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Generated SQL</CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="overflow-x-auto rounded-md bg-background border border-border p-4 text-sm leading-relaxed">
          <code>{highlightSQL(sql)}</code>
        </pre>
      </CardContent>
    </Card>
  );
}
