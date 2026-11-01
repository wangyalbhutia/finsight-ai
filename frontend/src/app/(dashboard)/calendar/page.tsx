"use client";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/hooks/useApi";
import { api, type CalendarEvent, type Reminder } from "@/lib/api";
import { inr } from "@/lib/utils";

const KIND_STYLE: Record<string, string> = {
  income: "bg-teal-600", subscription: "bg-violet-600", recurring: "bg-blue-600",
  reminder: "bg-amber-600", budget_reset: "bg-zinc-500", goal: "bg-pink-600",
};

function monthBounds(y: number, m: number) {
  const start = new Date(y, m, 1);
  const end = new Date(y, m + 1, 1);
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: iso(start), end: iso(end) };
}

export default function CalendarPage() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [selected, setSelected] = useState<string | null>(null);
  const bounds = useMemo(() => monthBounds(ym.y, ym.m), [ym]);
  const cal = useApi(() => api.calendarEvents(bounds.start, bounds.end).catch(() => null), [bounds.start, bounds.end]);
  const reminders = useApi(() => api.reminders().catch(() => [] as Reminder[]));
  const [form, setForm] = useState({ title: "", amount: "", due_date: "", recurrence: "none" });

  const byDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    (cal.data?.events ?? []).forEach((e) => { const arr = map.get(e.date) ?? []; arr.push(e); map.set(e.date, arr); });
    return map;
  }, [cal.data]);

  const first = new Date(ym.y, ym.m, 1);
  const daysInMonth = new Date(ym.y, ym.m + 1, 0).getDate();
  const leadBlanks = (first.getDay() + 6) % 7; // Monday-first grid
  const cells: (string | null)[] = [
    ...Array.from({ length: leadBlanks }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => `${ym.y}-${String(ym.m + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`),
  ];
  const monthName = first.toLocaleString("en-IN", { month: "long", year: "numeric" });
  const move = (delta: number) => { const d = new Date(ym.y, ym.m + delta, 1); setYm({ y: d.getFullYear(), m: d.getMonth() }); setSelected(null); };
  const dayEvents = selected ? byDate.get(selected) ?? [] : [];

  return <div>
    <h1 className="mb-2 text-3xl font-bold tracking-tight">Financial calendar</h1>
    <p className="mb-6 text-sm text-zinc-500">Salary expectations, subscriptions, recurring charges, budget resets, goal deadlines and your own reminders — each labelled by how certain it is. Detected items are patterns, not guarantees.</p>
    {cal.error && <ErrorState message={cal.error} onRetry={cal.reload} />}
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2"><CardHeader><CardTitle className="flex items-center justify-between"><span>{monthName}</span><span className="flex gap-2"><Button size="sm" variant="outline" onClick={() => move(-1)}>← Prev</Button><Button size="sm" variant="outline" onClick={() => move(1)}>Next →</Button></span></CardTitle></CardHeader><CardContent>
        {cal.loading ? <Skeleton className="h-80" /> : <>
          <div className="grid grid-cols-7 gap-1 text-center text-xs font-medium text-zinc-500">{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="py-1">{d}</div>)}</div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((iso, i) => iso === null ? <div key={i} /> : (
              <button key={iso} onClick={() => setSelected(iso)} className={`min-h-16 rounded-lg border p-1 text-left align-top text-xs ${selected === iso ? "border-teal-600 bg-teal-50 dark:bg-teal-950" : "border-zinc-200 dark:border-zinc-800"}`}>
                <span className="font-medium">{Number(iso.slice(8))}</span>
                {(byDate.get(iso) ?? []).slice(0, 3).map((e, j) => (<span key={j} className={`mt-0.5 block truncate rounded px-1 py-0.5 text-[10px] text-white ${KIND_STYLE[e.kind] ?? "bg-zinc-600"}`}>{e.title}</span>))}
                {(byDate.get(iso) ?? []).length > 3 && <span className="text-[10px] text-zinc-500">+{(byDate.get(iso) ?? []).length - 3} more</span>}
              </button>))}
          </div>
          {cal.data && <p className="mt-3 text-sm text-zinc-500">This month: expected income <b className="text-teal-700">{inr(cal.data.summary.expected_income)}</b> · expected obligations <b>{inr(cal.data.summary.expected_obligations)}</b> across {cal.data.count} events.</p>}
        </>}
      </CardContent></Card>
      <div className="space-y-4">
        <Card><CardHeader><CardTitle>{selected ? `Events on ${selected}` : "Upcoming this month"}</CardTitle></CardHeader><CardContent className="space-y-2">
          {(selected ? dayEvents : (cal.data?.events ?? []).slice(0, 10)).length ? (selected ? dayEvents : (cal.data?.events ?? []).slice(0, 10)).map((e, i) => (
            <div key={i} className="flex justify-between border-b pb-2 text-sm last:border-0"><span><span className="font-medium">{e.title}</span><span className="block text-zinc-500">{e.date} · {e.kind.replaceAll("_", " ")} · {e.certainty}</span></span><b className={e.kind === "income" ? "text-teal-700" : ""}>{e.amount != null ? `${e.kind === "income" ? "+" : "−"} ${inr(e.amount)}` : ""}</b></div>
          )) : <EmptyState title="No events" description="No events fall on this day/in this month yet." />}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Payment reminders</CardTitle></CardHeader><CardContent className="space-y-3">
          <form className="space-y-2" onSubmit={async (ev) => { ev.preventDefault(); await api.createReminder({ title: form.title, amount: form.amount ? Number(form.amount) : undefined, due_date: form.due_date, recurrence: form.recurrence }); setForm({ title: "", amount: "", due_date: "", recurrence: "none" }); reminders.reload(); cal.reload(); }}>
            <Input placeholder="Title (e.g. Electricity bill)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required aria-label="Reminder title" />
            <div className="flex gap-2"><Input type="number" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} aria-label="Amount" /><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} required aria-label="Due date" /></div>
            <select value={form.recurrence} onChange={(e) => setForm({ ...form, recurrence: e.target.value })} className="w-full rounded-md border bg-background px-2 py-2 text-sm" aria-label="Recurrence">
              <option value="none">One-time</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="yearly">Yearly</option>
            </select>
            <Button type="submit" className="w-full">Add reminder</Button>
          </form>
          {(reminders.data ?? []).length ? <ul className="space-y-2 text-sm">{(reminders.data ?? []).map((r) => (<li key={r.id} className="flex justify-between border-b pb-2 last:border-0"><span>{r.title}<span className="block text-zinc-500">{r.due_date} · {r.recurrence}{r.amount != null ? ` · ${inr(r.amount)}` : ""}</span></span><Button size="sm" variant="ghost" onClick={async () => { await api.deleteReminder(r.id); reminders.reload(); cal.reload(); }}>Delete</Button></li>))}</ul> : <p className="text-sm text-zinc-500">No reminders yet — add one above and it will appear on the calendar.</p>}
        </CardContent></Card>
      </div>
    </div>
  </div>;
}
