export interface ScenarioResult { category: string; reduction_percent: number; current: number; proposed: number; monthly_saving: number; annual_saving: number }
/** Pure math mirroring the backend simulator contract — used for instant preview and unit tests. Authoritative figures come from POST /simulator. */
export function computeScenario(category: string, currentMonthly: number, reductionPercent: number): ScenarioResult {
  const pct = Math.min(100, Math.max(0, reductionPercent));
  const proposed = +(currentMonthly * (1 - pct / 100)).toFixed(2);
  const monthly = +(currentMonthly - proposed).toFixed(2);
  return { category, reduction_percent: pct, current: currentMonthly, proposed, monthly_saving: monthly, annual_saving: +(monthly * 12).toFixed(2) };
}
