"use client";
import { api, normaliseList } from "@/lib/api"; import { useApi } from "./useApi";
export function useTransactions(params: Record<string,string|number|undefined> = {}) { const r=useApi(async()=>normaliseList(await api.transactions(params)),[JSON.stringify(params)]); return { transactions: r.data ?? [], ...r }; }
export function useAnalytics() { return useApi(async()=>{ const [summary,trends,categories]=await Promise.all([api.summary(),api.trends().catch(()=>[]),api.categorySpend().catch(()=>[])]); return {summary,trends,categories}; }); }
export function useBudgets() { const r=useApi(async()=>normaliseList(await api.budgets())); return { budgets:r.data??[], ...r }; }
export function useForecast(days=30) { return useApi(()=>api.forecast(days),[days]); }
export function useAnomalies() { const r=useApi(async()=>normaliseList(await api.anomalies())); return { anomalies:r.data??[], ...r }; }
