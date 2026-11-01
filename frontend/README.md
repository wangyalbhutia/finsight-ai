# FinSight AI — Frontend

Next.js (App Router) + TypeScript (strict) + Tailwind CSS. Premium minimal fintech UI, dark/light mode, Recharts, Framer Motion.

## Run
```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
npm install
npm run dev                  # http://localhost:3000
```

Backend must be running for live data. If the API is unreachable, pages show explicit error/empty states — no fake metrics are displayed.

## Verify
```bash
npx tsc --noEmit
npm run lint
npm run build
npm test        # Vitest: api client helpers + simulator math
```

## Structure
- `src/app/` — landing, `(auth)/login|register`, `(dashboard)/` layout + dashboard, transactions, analytics, predictions, budgets, assistant, simulator, reports, settings; `error.tsx` error boundary
- `src/lib/api.ts` — typed fetch client (JWT in localStorage, refresh stub/flow, 401 → /login), endpoints: auth, transactions (+import/export), categories/suggest, analytics/*, ml/forecast + ml/evaluation (with /predictions fallback), anomalies, budgets + budgets/status, assistant/chat, simulator, reports/* + export
- `src/types/` — User, Transaction, Category, Budget, AnalyticsSummary, Forecast, Anomaly, etc.
- `src/hooks/` — useAuth, useApi, useTransactions/useAnalytics/useBudgets/useForecast/useAnomalies
- `src/components/ui/` — shadcn-style button, card, input, table, skeleton, badge, progress
- `src/context/Providers.tsx` — Auth + Theme (class toggle, localStorage)
