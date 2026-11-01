export interface User { id: string; email: string; full_name?: string; name?: string; currency?: string; created_at?: string }
export type TransactionType = "income" | "expense" | "transfer";
export interface Category { id: string; name: string; type?: string; icon?: string; color?: string; user_id?: string }
export interface Transaction { id: string; user_id?: string; amount: number; type: TransactionType; category?: string; category_id?: string; category_name?: string; merchant?: string; description: string; note?: string; notes?: string; date: string; created_at?: string; is_recurring?: boolean }
export interface TransactionCreate { amount: number; type: TransactionType; description: string; category?: string; merchant?: string; note?: string; date: string }
export interface Paginated<T> { items: T[]; total: number; page: number; page_size?: number; size?: number }
export interface AnalyticsSummary { total_income: number; total_expense: number; total_expenditure?: number; net_balance: number; balance?: number; savings_rate: number; monthly_spending?: number; transaction_count?: number }
export interface TrendPoint { date: string; label?: string; income: number; expense: number; amount?: number }
export interface CategorySpend { name: string; category?: string; value: number; amount: number; percentage?: number }
export interface ForecastPoint { date: string; predicted: number; lower?: number; upper?: number; actual?: number }
export interface Forecast { horizon_days?: number; points?: ForecastPoint[]; forecast?: ForecastPoint[]; expected_monthly_expenditure?: number; end_of_month_spending?: number; model?: string; model_version?: string; generated_at?: string; metrics?: ModelMetrics; category_forecasts?: CategorySpend[] }
export interface ModelMetrics { mae?: number; rmse?: number; mape?: number | null; model?: string }
export interface Anomaly { id: string; transaction_id?: string; severity: "low"|"medium"|"high"|string; reason: string; description?: string; score?: number; confidence?: number; created_at?: string; detected_at?: string; status?: string; amount?: number; merchant?: string }
export interface Budget { id: string; category?: string; category_id?: string; name?: string; amount: number; limit_amount?: number; spent: number; remaining?: number; period?: string; month?: string; utilization?: number }
export interface BudgetCreate { category: string; amount: number; period: string }
export interface ChatMessage { role: "user"|"assistant"; content: string; created_at?: string }
export interface ChatResponse { answer?: string; response?: string; message?: string; insights?: string[]; data?: unknown }
export interface Scenario { id: string; category: string; reduction_percent: number; current: number; proposed: number; monthly_saving: number; annual_saving: number }
export interface ImportSummary { accepted: number; rejected: number; duplicates: number; errors?: string[] }
