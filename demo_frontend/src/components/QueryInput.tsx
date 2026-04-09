import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface QueryInputProps {
  onSubmit: (prompt: string) => void;
  disabled?: boolean;
}

export function QueryInput({ onSubmit, disabled }: QueryInputProps) {
  const [prompt, setPrompt] = useState("");

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
  );
}
