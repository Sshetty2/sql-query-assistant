import { useState, useEffect, useCallback } from "react";
import { fetchDatabases, fetchDatabaseSchema } from "@/api/client";
import type { DemoDatabase, SchemaTable } from "@/api/types";

export function useDatabase() {
  const [databases, setDatabases] = useState<DemoDatabase[]>([]);
  const [activeDbId, setActiveDbId] = useState<string | null>(null);
  const [schema, setSchema] = useState<SchemaTable[]>([]);
  const [loading, setLoading] = useState(true);

  // Load database list on mount
  useEffect(() => {
    fetchDatabases()
      .then((dbs) => {
        setDatabases(dbs);
        if (dbs.length > 0) {
          setActiveDbId(dbs[0].id);
        }
      })
      .catch(() => setDatabases([]))
      .finally(() => setLoading(false));
  }, []);

  // Fetch schema when active database changes
  useEffect(() => {
    if (!activeDbId) {
      setSchema([]);
      return;
    }

    setLoading(true);
    fetchDatabaseSchema(activeDbId)
      .then(setSchema)
      .catch(() => setSchema([]))
      .finally(() => setLoading(false));
  }, [activeDbId]);

  const switchDatabase = useCallback((id: string) => {
    setActiveDbId(id);
  }, []);

  return { databases, activeDbId, setActiveDbId: switchDatabase, schema, loading };
}
