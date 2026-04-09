import { useQuery } from "@/hooks/useQuery";
import { QueryInput } from "@/components/QueryInput";
import { WorkflowProgress } from "@/components/WorkflowProgress";
import { SqlViewer } from "@/components/SqlViewer";
import { ResultsTable } from "@/components/ResultsTable";
import { Card, CardContent } from "@/components/ui/card";

function App() {
  const { status, steps, result, error, execute } = useQuery();

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">SQL Query Assistant</h1>
          <p className="mt-1 text-muted-foreground">
            Ask questions about your data in plain English
          </p>
        </header>

        <div className="space-y-6">
          {/* Query input */}
          <QueryInput
            onSubmit={(prompt) => execute({ prompt })}
            disabled={status === "streaming"}
          />

          {/* Workflow progress */}
          {status === "streaming" && (
            <Card>
              <CardContent className="py-4">
                <p className="mb-3 text-sm font-medium text-muted-foreground">
                  Processing query...
                </p>
                <WorkflowProgress steps={steps} />
              </CardContent>
            </Card>
          )}

          {/* Error display */}
          {error && (
            <Card className="border-destructive">
              <CardContent className="py-4">
                <p className="text-sm text-destructive">{error}</p>
              </CardContent>
            </Card>
          )}

          {/* Results */}
          {result && (
            <div className="space-y-4">
              <SqlViewer sql={result.query} />
              <ResultsTable
                data={result.result}
                totalRecords={result.total_records_available}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
