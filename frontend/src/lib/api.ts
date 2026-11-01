import type { Anomaly, AnalyticsSummary, Budget, BudgetCreate, Category, CategorySpend, ChatResponse, Forecast, ImportSummary, Paginated, Transaction, TransactionCreate, TrendPoint, User } from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const TOKEN_KEY = "finsight_access_token";
const REFRESH_KEY = "finsight_refresh_token";

export function getToken(): string | null { if (typeof window === "undefined") return null; return localStorage.getItem(TOKEN_KEY); }
export function setTokens(access: string, refresh?: string) { localStorage.setItem(TOKEN_KEY, access); if (refresh) localStorage.setItem(REFRESH_KEY, refresh); }
export function clearTokens() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY); }

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function refreshAccessToken(): Promise<string | null> {
  const refresh = typeof window !== "undefined" ? localStorage.getItem(REFRESH_KEY) : null;
  if (!refresh) return null;
  try {
    const r = await fetch(`${API_URL}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refresh }) });
    if (!r.ok) return null;
    const d = (await r.json()) as { access_token: string; refresh_token?: string };
    setTokens(d.access_token, d.refresh_token); return d.access_token;
  } catch { return null; }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try { res = await fetch(`${API_URL}${path}`, { ...init, headers }); } catch { throw new ApiError(0, "Cannot reach the FinSight API. Check that the backend is running."); }
  if (res.status === 401 && retry) {
    const fresh = await refreshAccessToken();
    if (fresh) return apiFetch<T>(path, init, false);
    clearTokens(); if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) window.location.href = "/login";
    throw new ApiError(401, "Session expired. Please sign in again.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const j = (await res.json()) as { detail?: string | { msg: string }[]; message?: string }; msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map(d=>d.msg).join(", ") : j.message || msg; } catch {}
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? await res.json() : await res.text()) as T;
}

export async function downloadFile(path: string, filename: string, retry = true) {
  const token = getToken(); const res = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  // Downloads previously failed outright once the 30-minute access token
  // expired, even with a valid refresh token — refresh once, like apiFetch.
  if (res.status === 401 && retry) {
    const fresh = await refreshAccessToken();
    if (fresh) return downloadFile(path, filename, false);
    clearTokens(); if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) window.location.href = "/login";
    throw new ApiError(401, "Session expired. Please sign in again.");
  }
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}

const qs = (p: Record<string, string | number | undefined>) => { const u = new URLSearchParams(); Object.entries(p).forEach(([k,v])=>{ if(v!==undefined && v!=="") u.set(k,String(v)); }); const s=u.toString(); return s?`?${s}`:""; };

export interface HealthScore { score: number | null; grade: string | null; insufficient_data: boolean; message?: string; weakest_component?: string; components: Record<string, { score: number; weight: number; note: string; data_backed?: boolean }>; currency?: string; weights?: Record<string, number>; data_coverage_percent?: number; confidence?: string; disclaimer?: string }
export interface HealthHistory { snapshots: { date: string; score: number; grade: string; data_coverage_percent: number }[]; count: number; change: { delta: number; since: string; biggest_mover?: { component: string; direction: string } | null; explanation: string } | null; disclaimer?: string }
export interface CashflowTimeline { horizon_days: number; currency: string; insufficient_data: boolean; message?: string; events: { date: string; kind: string; label: string; amount: number; certainty: string }[]; daily: { date: string; balance: number; income: number; obligations: number; baseline_expense: number }[]; lowest_projected_balance?: { date: string; balance: number }; first_shortage_date?: string | null; end_of_month_balance?: number | null; totals?: { projected_income: number; projected_obligations: number; projected_baseline_expenses: number; projected_net: number; obligations_monthly_run_rate: number }; assumptions?: string[] }
export interface ProfileData { currency: string; insufficient_data: boolean; message?: string; data_gaps?: string[]; income_patterns?: { average_monthly_income: number; months_observed: number; regularity_label?: string | null; primary_source?: { merchant: string; typical_amount: number; typical_day_of_month: number } | null; sources: { merchant: string; total: number; share_percent: number }[] }; expense_patterns?: { average_monthly_expense: number; discretionary_share_percent: number; top_categories: { category: string; monthly_average: number; share_percent: number }[] }; spending_consistency?: { label?: string | null; monthly_cv?: number | null }; recurring_obligations?: { subscriptions_monthly_total: number; subscriptions_count: number; share_of_income_percent?: number | null }; savings_behavior?: { overall_savings_rate_percent: number; average_monthly_surplus: number; positive_months: number; total_months: number }; budget_adherence?: { budgets_this_month: number; average_utilisation_percent?: number | null }; goals?: { count: number; overall_progress_percent?: number | null; total_saved: number; total_target: number }; risk_indicators?: { type: string; severity: string; detail: string }[]; savings_opportunities?: { type: string; detail: string; estimated_monthly_saving?: number | null }[]; predicted_patterns?: { next_30d_expense_estimate?: number | null; expected_monthly_income?: number | null; basis?: string }; health_score?: number | null; health_grade?: string | null; note?: string }
export interface SmartInsight { type: string; severity: "warning" | "info" | "positive"; title: string; detail: string }
export interface Subscription { merchant: string; merchant_key: string; status: "potential" | "confirmed"; also_seen_as?: string[]; user_edited?: boolean; category_name?: string; frequency: string; average_amount: number; monthly_cost: number; annual_cost: number; next_expected_date?: string; price_change_percent?: number }
export interface CalendarEvent { date: string; title: string; kind: string; amount?: number | null; certainty: string; source: string }
export interface CalendarData { start: string; end: string; currency: string; events: CalendarEvent[]; count: number; summary: { expected_income: number; expected_obligations: number }; note?: string }
export interface Reminder { id: number; title: string; amount?: number | null; due_date: string; recurrence: string; category_name?: string; notes?: string }
export interface BudgetForecastItem { budget_id: number; category_name: string; limit_amount: number; spent: number; projected_month_end_spend: number; projected_utilisation_percent: number; safe_daily_allowance: number; risk: string }
export interface Cashflow { horizon_days: number; projected_income: number | null; projected_expense: number | null; projected_net: number | null; projected_savings_rate?: number | null; forecast_insufficient_data: boolean; note?: string }
export interface AffordResult { item_name: string; cost: number; requested_months: number; average_monthly_surplus: number; required_monthly_saving: number; feasible_within_requested_months: boolean; shortfall_per_month: number; months_needed_at_current_surplus: number | null; projected_affordable_date: string | null }

export const api = {
  login: (email: string, password: string) => apiFetch<{access_token:string;refresh_token?:string;user?:User}>("/auth/login", { method:"POST", body: JSON.stringify({email,password}) }),
  register: (name: string, email: string, password: string) => apiFetch<{access_token:string;refresh_token?:string;user?:User}>("/auth/register", { method:"POST", body: JSON.stringify({full_name:name,name,email,password}) }),
  me: () => apiFetch<User>("/auth/me"),
  logout: () => apiFetch<void>("/auth/logout", { method:"POST" }).catch(()=>undefined),
  updateProfile: (body: Partial<User>) => apiFetch<User>("/auth/me", { method:"PATCH", body: JSON.stringify(body) }),
  transactions: (params: Record<string,string|number|undefined> = {}) => apiFetch<Paginated<Transaction> | Transaction[]>(`/transactions${qs(params)}`),
  createTransaction: (b: TransactionCreate) => apiFetch<Transaction>("/transactions", { method:"POST", body: JSON.stringify(b) }),
  updateTransaction: (id: string, b: Partial<TransactionCreate>) => apiFetch<Transaction>(`/transactions/${id}`, { method:"PUT", body: JSON.stringify(b) }),
  deleteTransaction: (id: string) => apiFetch<void>(`/transactions/${id}`, { method:"DELETE" }),
  importTransactions: async (file: File): Promise<ImportSummary> => { const fd=new FormData(); fd.append("file",file); return apiFetch<ImportSummary>("/transactions/import", { method:"POST", body: fd }); },
  importStatement: async (file: File): Promise<ImportSummary & { statement_import_id?: number; format_detected?: string }> => { const fd=new FormData(); fd.append("file",file); return apiFetch("/transactions/import-statement", { method:"POST", body: fd }); },
  parseText: (text: string) => apiFetch<{ type: string; amount: number | null; currency: string; category_name: string; merchant: string; date: string; description: string; payment_method?: string | null; ambiguous_fields: string[] }>("/transactions/parse", { method:"POST", body: JSON.stringify({ text }) }),
  receiptParse: async (file: File) => { const fd=new FormData(); fd.append("file",file); return apiFetch<{ merchant: string; date?: string | null; amount?: number | null; description: string; ambiguous_fields: string[] }>("/transactions/receipt-parse", { method:"POST", body: fd }); },
  categories: () => apiFetch<Category[]>("/categories"),
  suggestCategory: async (description: string): Promise<{category:string;confidence?:number}|null> => {
    try { return await apiFetch<{category:string;confidence?:number}>("/categories/suggest", { method:"POST", body: JSON.stringify({ description, text: description }) }); }
    catch (e) { if (e instanceof ApiError && e.status===404) return apiFetch<{category:string;confidence?:number}>(`/categories/suggest?description=${encodeURIComponent(description)}`); throw e; }
  },
  exportTransactions: () => downloadFile("/transactions/export", "finsight-transactions.csv"),
  exportAccount: () => downloadFile("/account/export", "finsight-export.json"),
  memories: () => apiFetch<{ id: number; category: string; key: string; value: string }[]>("/memories"),
  saveMemory: (b: { category: string; key: string; value: string }) => apiFetch("/memories", { method: "POST", body: JSON.stringify(b) }),
  deleteMemory: (id: number) => apiFetch(`/memories/${id}`, { method: "DELETE" }),
  notifications: () => apiFetch<{ notifications: { id: number; kind: string; severity: string; title: string; body: string; is_read: boolean; created_at?: string }[]; unread_count: number }>("/notifications"),
  markNotificationRead: (id: number) => apiFetch(`/notifications/${id}/read`, { method: "POST" }),
  deleteAccount: () => apiFetch("/account", { method: "DELETE", body: JSON.stringify({ confirm: "DELETE" }) }),
  summary: (year?: number, month?: number) => apiFetch<AnalyticsSummary>(`/analytics/summary${year && month ? `?year=${year}&month=${month}` : ""}`),
  challenges: () => apiFetch<{ week_start: string; challenges: { id: string; title: string; detail: string; target_amount: number; progress_amount?: number | null; progress_percent?: number | null; status: string }[]; note?: string }>("/challenges"),
  // /analytics/trends returns a {daily, weekly, monthly} object, not an
  // array — normalise the monthly series into chart-ready TrendPoints.
  trends: async (): Promise<TrendPoint[]> => {
    const d = await apiFetch<{ monthly?: { month: string; total: number; income?: number; expense?: number }[] }>("/analytics/trends");
    return (d.monthly ?? []).map((p) => ({ date: p.month, income: p.income ?? 0, expense: p.expense ?? p.total, amount: p.expense ?? p.total }));
  },
  categorySpend: () => apiFetch<CategorySpend[]>("/analytics/categories"),
  // Weekly/monthly endpoints return {week|month, total, income, expense}
  // rows — charts expect {label, income, expense, amount} points.
  weekly: async (): Promise<TrendPoint[]> => {
    const rows = await apiFetch<{ week: string; total: number; income?: number; expense?: number }[]>("/analytics/weekly-pattern");
    return (rows ?? []).map((p) => ({ date: p.week, label: p.week, income: p.income ?? 0, expense: p.expense ?? p.total, amount: p.total }));
  },
  monthlyComparison: async (): Promise<TrendPoint[]> => {
    const rows = await apiFetch<{ month: string; total: number; income?: number; expense?: number }[]>("/analytics/monthly-comparison");
    return (rows ?? []).map((p) => ({ date: p.month, label: p.month, income: p.income ?? 0, expense: p.expense ?? p.total, amount: p.total }));
  },
  createRecurring: (b: { category_name: string; type: string; amount: number; merchant?: string; description?: string; frequency: string; next_date: string }) => apiFetch("/recurring", { method: "POST", body: JSON.stringify(b) }),
  goals: () => apiFetch<{ id: number; name: string; target_amount: number; current_amount: number }[]>("/goals"),
  createGoal: (b: { name: string; target_amount: number; current_amount?: number; deadline?: string }) => apiFetch("/goals", { method: "POST", body: JSON.stringify(b) }),
  deleteGoal: (id: number) => apiFetch(`/goals/${id}`, { method: "DELETE" }),
  goalForecast: (id: number) => apiFetch<{ goal_id: number; name: string; remaining: number; progress_percent: number; status: string; months_at_current_pace?: number | null; projected_completion_date?: string | null; required_monthly_contribution?: number | null; average_monthly_surplus?: number | null; message?: string }>(`/goals/${id}/forecast`),
  trajectory: (b: { category_name?: string; reduction_percent?: number; extra_monthly_savings?: number; income_change_percent?: number; one_off_expense?: number; months?: number }) => apiFetch<{ points: { month: string; baseline_balance: number; scenario_balance: number }[]; baseline_monthly_net: number; scenario_monthly_net: number; end_difference: number; assumptions: string[] }>("/simulator/trajectory", { method: "POST", body: JSON.stringify(b) }),
  modelEvaluation: () => apiFetch<{ rolling_origin?: { best_model?: string; origins?: number; models?: Record<string, { mae: number; rmse: number }> }; per_category?: { category: string; days: number; insufficient_data: boolean; best_model?: string | null; rolling_origin?: { models?: Record<string, { mae: number }> } }[]; evaluation_note?: string }>("/ml/evaluation"),
  forecast: async (days = 30): Promise<Forecast> => {
    let base: Forecast;
    try { base = await apiFetch<Forecast>(`/ml/forecast?horizon_days=${days}&days=${days}`); }
    catch (e) { if (e instanceof ApiError && (e.status===404||e.status===405)) base = await apiFetch<Forecast>(`/predictions/forecast?horizon_days=${days}`); else throw e; }
    // Category forecasts live on /ml/forecast/all — merge them in so the
    // Predictions page's category section has real data to show.
    try {
      const all = await apiFetch<{ category_forecasts?: { category?: string; category_name?: string; predicted_amount?: number | null }[]; category_wise?: { category?: string; category_name?: string; predicted_amount?: number | null }[] }>("/ml/forecast/all");
      const items = all.category_forecasts ?? all.category_wise ?? [];
      base.category_forecasts = items
        .filter((c) => c.predicted_amount != null)
        .map((c) => ({ name: c.category_name || c.category || "Category", category: c.category, value: c.predicted_amount as number, amount: c.predicted_amount as number }));
    } catch { /* category forecasts are optional — never fail the main forecast */ }
    return base;
  },
  evaluation: async (): Promise<import("@/types").ModelMetrics & {models?: import("@/types").ModelMetrics[]}> => {
    try { return await apiFetch("/ml/evaluation"); } catch (e) { if (e instanceof ApiError && e.status===404) return apiFetch("/predictions/evaluation"); throw e; }
  },
  anomalies: () => apiFetch<Anomaly[]>("/anomalies"),
  dismissAnomaly: (id: string) => apiFetch<void>(`/anomalies/${id}/dismiss`, { method:"POST" }).catch(()=>apiFetch<void>(`/anomalies/${id}/acknowledge`, { method:"POST" })),
  budgets: () => apiFetch<Budget[]>("/budgets"),
  budgetStatus: async (): Promise<Budget[]> => { try { const r=await apiFetch<Budget[]|{items:Budget[]}>("/budgets/status"); return Array.isArray(r)?r:r.items||[]; } catch(e){ if(e instanceof ApiError && e.status===404) return apiFetch<Budget[]>("/budgets"); throw e; } },
  reportsMonthly: (month?: string) => apiFetch<Record<string, unknown>>(`/reports/monthly${month?`?month=${encodeURIComponent(month)}`:""}`),
  reportsYearly: (year?: number) => apiFetch<Record<string, unknown>>(`/reports/yearly${year?`?year=${year}`:""}`),
  exportReport: (kind: "monthly"|"yearly", format: "csv"|"pdf") => downloadFile(`/reports/${kind}/export?format=${format}`, `finsight-${kind}-report.${format}`),
  createBudget: (b: BudgetCreate) => apiFetch<Budget>("/budgets", { method:"POST", body: JSON.stringify({category:b.category, amount:b.amount, limit_amount:b.amount, period:b.period}) }),
  updateBudget: (id: string, b: Partial<BudgetCreate>) => apiFetch<Budget>(`/budgets/${id}`, { method:"PUT", body: JSON.stringify(b) }),
  deleteBudget: (id: string) => apiFetch<void>(`/budgets/${id}`, { method:"DELETE" }),
  chat: (message: string) => apiFetch<ChatResponse>("/assistant/chat", { method:"POST", body: JSON.stringify({message}) }),
  simulate: (category: string, reduction_percent: number) => apiFetch<{current_spending:number;proposed_spending:number;monthly_savings:number;annual_savings:number;current?:number}>("/simulator", { method:"POST", body: JSON.stringify({category, reduction_percent, percentage: reduction_percent}) }),
  healthScore: () => apiFetch<HealthScore>("/analytics/health-score"),
  healthHistory: () => apiFetch<HealthHistory>("/analytics/health-score/history"),
  cashflowTimeline: (days = 30) => apiFetch<CashflowTimeline>(`/analytics/cashflow-timeline?horizon_days=${days}`),
  profile: async (): Promise<ProfileData> => { const r = await apiFetch<{ payload: ProfileData }>("/intelligence/profile"); return r.payload; },
  smartInsights: () => apiFetch<{insights: SmartInsight[]; count: number; insufficient_data: boolean}>("/analytics/insights"),
  subscriptions: () => apiFetch<{subscriptions: Subscription[]; count: number; confirmed_count?: number; potential_count?: number; total_monthly_cost: number; total_annual_cost: number; note?: string}>("/analytics/subscriptions"),
  subscriptionOverride: (merchant: string, body: { status: string; custom_amount?: number; custom_frequency?: string; custom_next_date?: string }) => apiFetch("/analytics/subscriptions/override", { method: "POST", body: JSON.stringify({ merchant, ...body }) }),
  removeSubscriptionOverride: (merchantKey: string) => apiFetch(`/analytics/subscriptions/override/${encodeURIComponent(merchantKey)}`, { method: "DELETE" }),
  calendarEvents: (start: string, end: string) => apiFetch<CalendarData>(`/calendar/events?start=${start}&end=${end}`),
  reminders: () => apiFetch<Reminder[]>("/calendar/reminders"),
  createReminder: (b: { title: string; amount?: number; due_date: string; recurrence: string; category_name?: string }) => apiFetch<Reminder>("/calendar/reminders", { method: "POST", body: JSON.stringify(b) }),
  updateReminder: (id: number, b: { title: string; amount?: number; due_date: string; recurrence: string; category_name?: string }) => apiFetch<Reminder>(`/calendar/reminders/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteReminder: (id: number) => apiFetch(`/calendar/reminders/${id}`, { method: "DELETE" }),
  budgetForecast: () => apiFetch<{budgets: BudgetForecastItem[]; month: number; year: number; high_risk_count: number}>("/budgets/forecast"),
  cashflow: (days = 30) => apiFetch<Cashflow>(`/ml/cashflow?horizon_days=${days}`),
  afford: (item_name: string, cost: number, months: number) => apiFetch<AffordResult>("/simulator/afford", { method:"POST", body: JSON.stringify({item_name, cost, months}) }),
  autoCategorize: (id: string) => apiFetch<Transaction & {applied: boolean}>(`/transactions/${id}/auto-categorize`, { method:"POST" }),
};
export function normaliseList<T>(data: Paginated<T> | T[] | null | undefined): T[] { if (!data) return []; return Array.isArray(data) ? data : data.items || []; }
