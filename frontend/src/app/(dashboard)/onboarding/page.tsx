"use client";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const STEPS = ["About you", "Your income", "First budget", "First goal", "Bring your data"];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [income, setIncome] = useState({ amount: "", employer: "", payday: "1" });
  const [budget, setBudget] = useState({ category: "Food & Dining", amount: "" });
  const [goal, setGoal] = useState({ name: "Emergency fund", target: "", deadline: "" });

  async function saveStep() {
    setMsg(""); setBusy(true);
    try {
      if (step === 0) {
        if (name.trim()) await api.saveMemory({ category: "preference", key: "preferred_name", value: name.trim() });
        await api.saveMemory({ category: "preference", key: "primary_currency", value: currency });
        setMsg("Saved. You can change or delete this any time on your Profile page.");
      } else if (step === 1) {
        const amt = Number(income.amount);
        if (amt > 0) {
          const now = new Date();
          const next = new Date(now.getFullYear(), now.getMonth() + (now.getDate() >= Number(income.payday) ? 1 : 0), Number(income.payday));
          await api.createRecurring({ category_name: "Salary", type: "income", amount: amt, merchant: income.employer || "Employer", description: "Monthly salary", frequency: "monthly", next_date: next.toISOString().slice(0, 10) });
          setMsg("Salary schedule saved — it will appear on your Calendar as a confirmed event.");
        } else setMsg("Skipped — add income later from Transactions.");
      } else if (step === 2) {
        const amt = Number(budget.amount);
        if (amt > 0) { await api.createBudget({ category: budget.category, amount: amt, period: "monthly" }); setMsg("Budget created for this month."); }
        else setMsg("Skipped — budgets can be added any time.");
      } else if (step === 3) {
        const amt = Number(goal.target);
        if (amt > 0) { await api.createGoal({ name: goal.name, target_amount: amt, deadline: goal.deadline || undefined }); setMsg("Goal created — its forecast lives on the Budgets page."); }
        else setMsg("Skipped — goals can be added any time.");
      }
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not save this step — you can continue and add it later."); }
    finally { setBusy(false); }
  }

  return <div className="mx-auto max-w-2xl">
    <h1 className="mb-2 text-3xl font-bold tracking-tight">Getting started</h1>
    <p className="mb-6 text-sm text-zinc-500">Five short steps. Everything is optional and editable later — FinSight only ever computes from data you actually provide.</p>
    <div className="mb-6 flex flex-wrap gap-2">{STEPS.map((label, i) => (<button key={label} onClick={() => setStep(i)} className={`rounded-full border px-3 py-1 text-sm ${i === step ? "border-teal-600 bg-teal-600 text-white" : i < step ? "border-teal-600 text-teal-700" : "text-zinc-500"}`}>{i + 1}. {label}</button>))}</div>
    <Card><CardHeader><CardTitle>{STEPS[step]}</CardTitle></CardHeader><CardContent className="space-y-4">
      {step === 0 && <><label className="block text-sm">What should FinSight call you?<Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" className="mt-1" /></label>
        <label className="block text-sm">Primary currency<select value={currency} onChange={(e) => setCurrency(e.target.value)} className="mt-1 w-full rounded-md border bg-background px-2 py-2 text-sm"><option value="INR">INR — Indian Rupee (₹)</option><option value="USD">USD — US Dollar ($)</option><option value="EUR">EUR — Euro (€)</option><option value="GBP">GBP — British Pound (£)</option></select></label>
        <p className="text-xs text-zinc-500">Stored as a preference you own (Profile → What FinSight remembers). Headline totals always use the currency most of your transactions are in; other currencies are never silently mixed in.</p></>}
      {step === 1 && <><label className="block text-sm">Monthly take-home income (₹)<Input type="number" value={income.amount} onChange={(e) => setIncome({ ...income, amount: e.target.value })} placeholder="e.g. 85000" className="mt-1" /></label>
        <label className="block text-sm">Employer / source<Input value={income.employer} onChange={(e) => setIncome({ ...income, employer: e.target.value })} placeholder="e.g. TechCorp India" className="mt-1" /></label>
        <label className="block text-sm">Payday (day of month)<Input type="number" min="1" max="28" value={income.payday} onChange={(e) => setIncome({ ...income, payday: e.target.value })} className="mt-1" /></label>
        <p className="text-xs text-zinc-500">This creates a scheduled income entry on your Calendar. It does not fabricate transactions — your actual salary credits still come from your records.</p></>}
      {step === 2 && <><label className="block text-sm">Category<Input value={budget.category} onChange={(e) => setBudget({ ...budget, category: e.target.value })} className="mt-1" /></label>
        <label className="block text-sm">Monthly limit (₹)<Input type="number" value={budget.amount} onChange={(e) => setBudget({ ...budget, amount: e.target.value })} placeholder="e.g. 15000" className="mt-1" /></label>
        <p className="text-xs text-zinc-500">Budgets power your health score, month-end forecasts and briefing alerts.</p></>}
      {step === 3 && <><label className="block text-sm">Goal name<Input value={goal.name} onChange={(e) => setGoal({ ...goal, name: e.target.value })} className="mt-1" /></label>
        <label className="block text-sm">Target amount (₹)<Input type="number" value={goal.target} onChange={(e) => setGoal({ ...goal, target: e.target.value })} placeholder="e.g. 300000" className="mt-1" /></label>
        <label className="block text-sm">Deadline (optional)<Input type="date" value={goal.deadline} onChange={(e) => setGoal({ ...goal, deadline: e.target.value })} className="mt-1" /></label>
        <p className="text-xs text-zinc-500">Once you have a few months of history, FinSight forecasts the completion date from your real average surplus.</p></>}
      {step === 4 && <div className="space-y-3 text-sm"><p>Choose how your history arrives:</p>
        <ul className="list-disc space-y-2 pl-5">
          <li><Link href="/transactions" className="text-teal-700 underline">Import a bank/UPI statement CSV</Link> — the fastest way to a full picture (Transactions → Import statement).</li>
          <li><Link href="/transactions" className="text-teal-700 underline">Import the FinSight CSV format</Link> — if you keep your own spreadsheet.</li>
          <li><Link href="/transactions" className="text-teal-700 underline">Quick-add by typing</Link> — “Spent ₹250 on lunch today” is enough.</li>
        </ul>
        <p className="text-zinc-500">Then open <Link href="/profile" className="text-teal-700 underline">your financial Profile</Link> — your digital twin builds itself from whatever data exists and honestly labels what it cannot assess yet.</p></div>}
      {msg && <p className="text-sm text-teal-700 dark:text-teal-300">{msg}</p>}
      <div className="flex items-center justify-between pt-2">
        <Button variant="ghost" disabled={step === 0} onClick={() => { setStep(step - 1); setMsg(""); }}>Back</Button>
        <div className="flex gap-2">
          {step < 4 && <Button variant="outline" onClick={() => { setStep(step + 1); setMsg(""); }}>Skip</Button>}
          {step < 4 ? <Button disabled={busy} onClick={async () => { await saveStep(); setStep(step + 1); }}>Save & continue</Button> : <Link href="/dashboard"><Button>Go to dashboard</Button></Link>}
        </div>
      </div>
    </CardContent></Card>
  </div>;
}
