"use client";
import { useCallback, useEffect, useState } from "react";
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data,setData]=useState<T|null>(null); const [loading,setLoading]=useState(true); const [error,setError]=useState<string|null>(null);
  const reload=useCallback(async()=>{ setLoading(true); setError(null); try{ setData(await fetcher()); }catch(e){ setError(e instanceof Error?e.message:"Failed to load"); } finally{ setLoading(false); } // eslint-disable-next-line react-hooks/exhaustive-deps
  },deps);
  useEffect(()=>{ void reload(); },[reload]);
  return { data, loading, error, reload, setData };
}
