import { describe, expect, it, vi } from "vitest";
import { ApiError, api, normaliseList } from "./api";
describe("api client helpers", () => {
  it("normaliseList unwraps paginated and plain arrays", () => { expect(normaliseList([1,2])).toEqual([1,2]); expect(normaliseList({ items:[3], total:1, page:1 })).toEqual([3]); expect(normaliseList(null)).toEqual([]); });
  it("ApiError carries status", () => { const e=new ApiError(401,"nope"); expect(e.status).toBe(401); expect(e.message).toBe("nope"); });
});

// Regression tests for the chart data-mapping fixes: the backend returns
// objects/series with {month|week, total, income, expense} shapes, while
// the charts consume TrendPoint[] {date, label, income, expense, amount}.
function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const key = Object.keys(routes).find((k) => String(url).includes(k));
    if (!key) throw new Error(`unstubbed fetch: ${url}`);
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => routes[key] } as unknown as Response;
  }));
}
describe("chart data mapping", () => {
  it("trends() normalises the monthly series object into points", async () => {
    stubFetch({ "/analytics/trends": { monthly: [{ month: "2026-05", total: 100, income: 500, expense: 100 }] } });
    const pts = await api.trends();
    expect(pts).toEqual([{ date: "2026-05", income: 500, expense: 100, amount: 100 }]);
  });
  it("weekly() maps week rows to labelled points", async () => {
    stubFetch({ "/analytics/weekly-pattern": [{ week: "2026-W18", total: 42, income: 7, expense: 42 }] });
    const pts = await api.weekly();
    expect(pts[0].label).toBe("2026-W18"); expect(pts[0].expense).toBe(42); expect(pts[0].amount).toBe(42);
  });
  it("monthlyComparison() maps month rows to labelled points", async () => {
    stubFetch({ "/analytics/monthly-comparison": [{ month: "2026-05", total: 9, income: 90, expense: 9 }] });
    const pts = await api.monthlyComparison();
    expect(pts[0].label).toBe("2026-05"); expect(pts[0].income).toBe(90);
  });
  it("forecast() merges category forecasts, dropping insufficient ones", async () => {
    stubFetch({
      "/ml/forecast?": { points: [], predicted_amount: 123 },
      "/ml/forecast/all": { category_forecasts: [
        { category: "Groceries", category_name: "Groceries", predicted_amount: 25588.8 },
        { category: "Travel", category_name: "Travel", predicted_amount: null },
      ] },
    });
    const f = await api.forecast(30);
    expect(f.category_forecasts).toEqual([{ name: "Groceries", category: "Groceries", value: 25588.8, amount: 25588.8 }]);
  });
});
