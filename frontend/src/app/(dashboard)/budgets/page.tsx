"use client";
import { useEffect, useState } from "react"; import { Button } from "@/components/ui/button"; import { Input, Label, Select } from "@/components/ui/input"; import { Card, CardContent } from "@/components/ui/card"; import { Progress } from "@/components/ui/progress"; import { Badge } from "@/components/ui/badge"; import { EmptyState, ErrorState, Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/hooks/useApi"; import { api } from "@/lib/api"; import { inr } from "@/lib/utils"; import type { Budget } from "@/types";
function alertBadge(util:number){ if(util>=100) return <Badge variant="destructive">100% — exceeded</Badge>; if(util>=90) return <Badge variant="destructive">90% alert</Badge>; if(util>=75) return <Badge>75% alert</Badge>; if(util>=50) return <Badge variant="secondary">50% reached</Badge>; return <Badge variant="outline">On track</Badge>; }
export default function Budgets(){
 const q=useApi<Budget[]>(async()=>{ try{ return await api.budgetStatus(); }catch{ return (await api.budgets()) as Budget[]; } });
 const budgets=q.data??[]; const [category,setCategory]=useState("Food"); const [amount,setAmount]=useState(""); const [period,setPeriod]=useState("monthly"); const [err,setErr]=useState(""); const [editing,setEditing]=useState<string|null>(null);
 useEffect(()=>{},[]);
 async function submit(e:React.FormEvent){ e.preventDefault(); setErr(""); if(!category.trim()||!(Number(amount)>0)){setErr("Enter a category and an amount greater than zero.");return;} try{ if(editing) await api.updateBudget(editing,{category,amount:Number(amount),period}); else await api.createBudget({category,amount:Number(amount),period}); setAmount(""); setEditing(null); await q.reload(); }catch(ex){ setErr(ex instanceof Error?ex.message:"Could not save budget"); } }
 return <div><h1 className="mb-6 text-3xl font-bold tracking-tight">Budgets</h1>
 <Card className="mb-4"><CardContent className="pt-5"><form onSubmit={submit} className="flex flex-wrap items-end gap-3"><div><Label>Category</Label><Input value={category} onChange={e=>setCategory(e.target.value)}/></div><div><Label>Limit (₹)</Label><Input type="number" min="0" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></div><div><Label>Period</Label><Select value={period} onChange={e=>setPeriod(e.target.value)}><option value="monthly">Monthly</option><option value="weekly">Weekly</option></Select></div><Button>{editing?"Save budget":"Create budget"}</Button>{editing&&<Button type="button" variant="ghost" onClick={()=>setEditing(null)}>Cancel edit</Button>}{err&&<p role="alert" className="w-full text-sm text-red-600">{err}</p>}</form></CardContent></Card>
 {q.loading?<div className="space-y-3"><Skeleton className="h-24"/><Skeleton className="h-24"/></div>:q.error?<ErrorState message={q.error} onRetry={q.reload}/>:budgets.length===0?<EmptyState title="No budgets yet" description="Create your first monthly or category budget above. Alerts trigger at 50%, 75%, 90% and 100% utilisation, plus forecast-based overrun warnings."/>:
 <div className="grid gap-4 sm:grid-cols-2">{budgets.map(b=>{ const lim=b.amount||b.limit_amount||0; let util=b.utilization??(lim?b.spent/lim:0); if(util<=1) util=util*100; const remaining=b.remaining??(lim-b.spent); return <Card key={b.id}><CardContent className="pt-5"><div className="flex items-start justify-between gap-2"><div><p className="font-semibold">{b.category||b.name||"Budget"}</p><p className="text-sm text-zinc-500">{b.period||"monthly"} · {inr(b.spent)} spent of {inr(lim)}</p></div>{alertBadge(util)}</div><Progress value={util} className="mt-3"/><p className="mt-2 text-sm">{remaining>=0?`${inr(remaining)} remaining`:`${inr(Math.abs(remaining))} over budget`} · {Math.round(util)}% used</p><div className="mt-3 flex gap-2"><Button size="sm" variant="outline" onClick={()=>{setEditing(b.id);setCategory(b.category||b.name||"");setAmount(String(lim));}}>Edit</Button><Button size="sm" variant="destructive" onClick={async()=>{ await api.deleteBudget(b.id); await q.reload(); }}>Delete</Button></div></CardContent></Card>; })}</div>}
 <GoalsSection/>
 </div>; }


function GoalsSection() {
  const goals = useApi(() => api.goals().catch(() => []), []);
  const [form, setForm] = useState({ name: "", target_amount: "", current_amount: "", deadline: "" });
  const [forecasts, setForecasts] = useState<Record<number, string>>({});
  async function loadForecast(id: number) {
    try { const f = await api.goalForecast(id);
      setForecasts((prev) => ({ ...prev, [id]: f.status === "achieved" ? "Achieved 🎉" : f.status === "cannot_project" ? (f.message || "Cannot project yet") : `At your recent surplus pace: ~${f.months_at_current_pace} month(s) → ${f.projected_completion_date}. ${f.required_monthly_contribution != null ? `Deadline needs ${inr(f.required_monthly_contribution)}/month.` : ""} (${f.status.replaceAll("_", " ")})` }));
    } catch { setForecasts((prev) => ({ ...prev, [id]: "Forecast unavailable" })); }
  }
  return <div className="mt-8"><h2 className="mb-4 text-2xl font-bold tracking-tight">Savings goals</h2>
    <form className="mb-4 flex flex-wrap gap-2" onSubmit={async (e) => { e.preventDefault(); await api.createGoal({ name: form.name, target_amount: Number(form.target_amount), current_amount: Number(form.current_amount) || 0, deadline: form.deadline || undefined }); setForm({ name: "", target_amount: "", current_amount: "", deadline: "" }); goals.reload(); }}>
      <Input placeholder="Goal name (e.g. Emergency fund)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required className="w-52" aria-label="Goal name" />
      <Input type="number" placeholder="Target ₹" value={form.target_amount} onChange={(e) => setForm({ ...form, target_amount: e.target.value })} required className="w-32" aria-label="Target amount" />
      <Input type="number" placeholder="Saved so far ₹" value={form.current_amount} onChange={(e) => setForm({ ...form, current_amount: e.target.value })} className="w-36" aria-label="Current amount" />
      <Input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} className="w-40" aria-label="Deadline" />
      <Button type="submit">Add goal</Button>
    </form>
    {(goals.data ?? []).length ? <div className="grid gap-4 md:grid-cols-2">{(goals.data ?? []).map((g) => (<Card key={g.id}><CardContent className="pt-4"><div className="flex items-start justify-between"><div><p className="font-semibold">{g.name}</p><p className="text-sm text-zinc-500">{inr(g.current_amount)} of {inr(g.target_amount)} ({g.target_amount ? Math.round(g.current_amount / g.target_amount * 100) : 0}%)</p></div><Button size="sm" variant="ghost" onClick={async () => { await api.deleteGoal(g.id); goals.reload(); }}>Delete</Button></div><Progress value={g.target_amount ? Math.min(100, g.current_amount / g.target_amount * 100) : 0} className="my-3" />{forecasts[g.id] ? <p className="text-sm text-zinc-600 dark:text-zinc-300">{forecasts[g.id]}</p> : <Button size="sm" variant="outline" onClick={() => void loadForecast(g.id)}>Forecast completion</Button>}</CardContent></Card>))}</div> : <p className="text-sm text-zinc-500">No goals yet — add your first one above. Forecasts use your recent average monthly surplus and never invent a date when there is no surplus.</p>}
  </div>;
}
