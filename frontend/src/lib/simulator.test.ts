import { describe, expect, it } from "vitest";
import { computeScenario } from "./simulator";
describe("computeScenario", () => {
  it("reduces by 20% and annualises", () => { const r = computeScenario("Food", 10000, 20); expect(r.proposed).toBe(8000); expect(r.monthly_saving).toBe(2000); expect(r.annual_saving).toBe(24000); });
  it("clamps percentage to 0-100", () => { expect(computeScenario("Food", 5000, 150).proposed).toBe(0); expect(computeScenario("Food", 5000, -10).proposed).toBe(5000); });
  it("zero reduction saves nothing", () => { expect(computeScenario("Rent", 15000, 0).monthly_saving).toBe(0); });
});
