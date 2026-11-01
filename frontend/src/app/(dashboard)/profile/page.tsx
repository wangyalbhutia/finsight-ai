"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"; import { Button } from "@/components/ui/button"; import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/skeleton";
import { useState } from "react";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { inr } from "@/lib/utils";

// Financial Profile (Digital Twin): every figure is computed from the
// user's own transaction records by the Intelligence Engine. Inferred
// patterns name their evidence; missing history shows as a labelled gap.
export default function Profile() {
  const q = useApi(() => api.profile());
  if (q.loading) return <><h1 className="mb-6 text-3xl font-bold">Financial profile</h1><Skeleton className="h-72" /></>;
  if (q.error || !q.data) return <><h1 className="mb-6 text-3xl font-bold">Financial profile</h1><ErrorState message={q.error || "Profile unavailable."} onRetry={q.reload} /></>;
  const p = q.data;
  if (p.insufficient_data) return <><h1 className="mb-6 text-3xl font-bold">Financial profile</h1><EmptyState title="No profile yet" description={p.message || "Add or import transactions and your profile will be built from them — nothing is invented."} /></>;

  const ip = p.income_patterns; const ep = p.expense_patterns; const sb = p.savings_behavior;
  const ro = p.recurring_obligations; const ba = p.budget_adherence; const gl = p.goals; const pp = p.predicted_patterns;
  return <div>
    <h1 className="mb-2 text-3xl font-bold tracking-tight">Financial profile</h1>
    <p className="mb-6 text-sm text-zinc-500">Your digital twin — computed from your records only. Health score: <b>{p.health_score ?? "—"}</b>{p.health_grade ? ` (grade ${p.health_grade})` : ""}. {p.note}</p>
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Income patterns</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        <p className="flex justify-between"><span>Average monthly income</span><b>{inr(ip?.average_monthly_income || 0)}</b></p>
        <p className="flex justify-between"><span>Months observed</span><b>{ip?.months_observed}</b></p>
        <p className="flex justify-between"><span>Regularity</span><b>{ip?.regularity_label || "not assessable yet"}</b></p>
        {ip?.primary_source ? <p className="flex justify-between"><span>Main source (detected)</span><b>{ip.primary_source.merchant} · {inr(ip.primary_source.typical_amount)} around day {ip.primary_source.typical_day_of_month}</b></p> : <p className="text-zinc-500">No dominant monthly income pattern detected.</p>}
        {ip?.sources?.length ? <div className="pt-2">{ip.sources.slice(0, 4).map((s, i) => (<p key={i} className="flex justify-between text-zinc-500"><span>{s.merchant}</span><span>{s.share_percent}% of income</span></p>))}</div> : null}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Spending patterns</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        <p className="flex justify-between"><span>Average monthly expense</span><b>{inr(ep?.average_monthly_expense || 0)}</b></p>
        <p className="flex justify-between"><span>Consistency</span><b>{p.spending_consistency?.label || "not assessable yet"}</b></p>
        <p className="flex justify-between"><span>Discretionary share</span><b>{ep?.discretionary_share_percent ?? 0}%</b></p>
        {ep?.top_categories?.length ? <div className="pt-2">{ep.top_categories.map((c, i) => (<p key={i} className="flex justify-between text-zinc-500"><span>{c.category}</span><span>{inr(c.monthly_average)}/mo · {c.share_percent}%</span></p>))}</div> : null}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Obligations & budgets</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        <p className="flex justify-between"><span>Detected subscriptions</span><b>{ro?.subscriptions_count} · {inr(ro?.subscriptions_monthly_total || 0)}/mo</b></p>
        <p className="flex justify-between"><span>Share of income</span><b>{ro?.share_of_income_percent ?? "—"}%</b></p>
        <p className="flex justify-between"><span>Budgets this month</span><b>{ba?.budgets_this_month}</b></p>
        <p className="flex justify-between"><span>Average budget use</span><b>{ba?.average_utilisation_percent != null ? `${ba.average_utilisation_percent}%` : "not assessed"}</b></p>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Savings & goals</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        <p className="flex justify-between"><span>Savings rate</span><b>{sb?.overall_savings_rate_percent ?? 0}%</b></p>
        <p className="flex justify-between"><span>Average monthly surplus</span><b>{inr(sb?.average_monthly_surplus || 0)}</b></p>
        <p className="flex justify-between"><span>Positive months</span><b>{sb?.positive_months} of {sb?.total_months}</b></p>
        <p className="flex justify-between"><span>Goals</span><b>{gl?.count ? `${gl.count} · ${gl.overall_progress_percent}% funded (${inr(gl.total_saved)} of ${inr(gl.total_target)})` : "none yet"}</b></p>
        {pp && <p className="flex justify-between"><span>Next-30-day expense estimate</span><b>{pp.next_30d_expense_estimate != null ? inr(pp.next_30d_expense_estimate) : "insufficient history"}</b></p>}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Risk indicators</CardTitle></CardHeader><CardContent className="space-y-2">{p.risk_indicators?.length ? p.risk_indicators.map((r, i) => (<div key={i} className="rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-900"><p className="font-medium">{r.severity === "high" ? "⚠ " : ""}{r.type.replaceAll("_", " ")}</p><p className="text-zinc-500">{r.detail}</p></div>)) : <EmptyState title="No risk indicators" description="No deterministic risk rules are currently triggered by your data." />}</CardContent></Card>
      <Card><CardHeader><CardTitle>Savings opportunities</CardTitle></CardHeader><CardContent className="space-y-2">{p.savings_opportunities?.length ? p.savings_opportunities.map((o, i) => (<div key={i} className="rounded-xl bg-teal-50 p-3 text-sm dark:bg-teal-950"><p>{o.detail}</p>{o.estimated_monthly_saving != null && <p className="mt-1 font-semibold">≈ {inr(o.estimated_monthly_saving)}/month</p>}</div>)) : <EmptyState title="No opportunities identified yet" description="Opportunities appear when patterns in your data support a concrete, evidenced suggestion." />}</CardContent></Card>
    </div>
    <MemoriesCard />
    {p.data_gaps?.length ? <Card className="mt-4"><CardHeader><CardTitle>What cannot be assessed yet</CardTitle></CardHeader><CardContent><ul className="list-disc space-y-1 pl-5 text-sm text-zinc-500">{p.data_gaps.map((g, i) => <li key={i}>{g}</li>)}</ul></CardContent></Card> : null}
  </div>;
}


function MemoriesCard() {
  const mem = useApi(() => api.memories().catch(() => []), []);
  const [form, setForm] = useState({ category: "preference", key: "", value: "" });
  return <Card className="mt-4"><CardHeader><CardTitle>What FinSight remembers about you</CardTitle></CardHeader><CardContent>
    <p className="mb-3 text-sm text-zinc-500">Only what you save here — nothing is stored silently. Merchant corrections change how future transactions are categorised; everything can be deleted at any time.</p>
    {(mem.data ?? []).length ? <ul className="mb-4 space-y-2 text-sm">{(mem.data ?? []).map((m) => (<li key={m.id} className="flex items-center justify-between border-b pb-2 last:border-0"><span><b>{m.key}</b> <span className="text-zinc-400">({m.category.replaceAll("_", " ")})</span><span className="block text-zinc-500">{m.value}</span></span><Button size="sm" variant="ghost" onClick={async () => { await api.deleteMemory(m.id); mem.reload(); }}>Delete</Button></li>))}</ul> : <p className="mb-4 text-sm text-zinc-500">Nothing stored yet.</p>}
    <form className="flex flex-wrap gap-2" onSubmit={async (e) => { e.preventDefault(); await api.saveMemory(form); setForm({ category: "preference", key: "", value: "" }); mem.reload(); }}>
      <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="rounded-md border bg-background px-2 py-2 text-sm" aria-label="Memory type">
        <option value="preference">Preference</option><option value="merchant_correction">Merchant correction</option><option value="life_event">Life event</option><option value="note">Note</option>
      </select>
      <Input placeholder={form.category === "merchant_correction" ? "Merchant (e.g. swiggy)" : "Name (e.g. preferred name)"} value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} required className="w-48" aria-label="Memory key" />
      <Input placeholder={form.category === "merchant_correction" ? "Category (e.g. Food & Dining)" : "Value"} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} required className="w-56" aria-label="Memory value" />
      <Button type="submit">Save</Button>
    </form>
  </CardContent></Card>;
}
