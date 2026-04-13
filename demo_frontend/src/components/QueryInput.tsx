import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const SAMPLE_QUESTIONS: Record<string, string[]> = {
  demo_db_1: [
    "Show me the top 10 best-selling tracks by total revenue",
    "Which artists have the most albums?",
    "Total sales by country for the last year",
    "List all employees and the customers they support",
  ],
  demo_db_2: [
    "Top 10 customers by total order value",
    "Which products are running low on stock?",
    "Monthly revenue trend by product category",
    "Show orders that shipped late with customer and shipper details",
  ],
  demo_db_3: [
    "Which actors have appeared in the most films?",
    "Top 10 customers by total rental payments",
    "Show film inventory count by store and category",
    "List overdue rentals with customer contact details",
  ],
};

interface QueryInputProps {
  onSubmit: (prompt: string) => void;
  disabled?: boolean;
  activeDbId?: string | null;
}

export function QueryInput({ onSubmit, disabled, activeDbId }: QueryInputProps) {
  const [prompt, setPrompt] = useState("");

  const suggestions = activeDbId ? SAMPLE_QUESTIONS[activeDbId] ?? [] : [];

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="space-y-2">
      <form onSubmit={handleSubmit} className="flex gap-3 items-end">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data..."
          disabled={disabled}
          className="min-h-[60px] resize-none flex-1"
          rows={2}
        />
        <Button type="submit" disabled={disabled || !prompt.trim()} className="h-[60px] px-6">
          {disabled ? "Running..." : "Query"}
        </Button>
      </form>
      {suggestions.length > 0 && !disabled && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setPrompt(q)}
              className="text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
