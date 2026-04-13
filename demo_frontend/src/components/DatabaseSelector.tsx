import { Database } from "lucide-react";
import type { DemoDatabase } from "@/api/types";

interface DatabaseSelectorProps {
  databases: DemoDatabase[];
  activeDbId: string | null;
  onSelect: (id: string) => void;
}

export function DatabaseSelector({ databases, activeDbId, onSelect }: DatabaseSelectorProps) {
  if (databases.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <Database className="h-4 w-4 text-muted-foreground" />
      <select
        value={activeDbId ?? ""}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-md border border-border bg-input px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {databases.map((db) => (
          <option key={db.id} value={db.id}>
            {db.name} — {db.description}
          </option>
        ))}
      </select>
    </div>
  );
}
