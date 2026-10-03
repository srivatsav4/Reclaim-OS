import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FlaskConical, Play, RotateCcw } from "lucide-react";
import { api, useAsync } from "../api";
import { humanize, inr, lakh, pct } from "../format";
import { Badge, Card, ErrorBox, Metric, PageHeader, SimTag, Spinner, C, tooltipStyle } from "../components/ui";

const axis = { stroke: "#475569", fontSize: 11, tickLine: false, axisLine: false } as const;

function Funnel({ stages }: { stages: { stage: string; cases: number; amount: number }[] }) {
  const max = stages[0]?.amount || 1;
  const colors = [C.slate, C.blue, C.cyan, C.green];
  return (
    <div className="space-y-2.5">
      {stages.map((s, i) => (
        <div key={s.stage}>
          <div className="mb-1 flex justify-between text-xs"><span className="label !text-slate-400">{s.stage.replace("_", " ")}</span><span className="num text-slate-300">{lakh(s.amount)} <span className="text-slate-600">· {s.cases} cases</span></span></div>
          <div className="h-7 rounded-lg bg-white/[0.04]"><div className="h-7 rounded-lg transition-all duration-700" style={{ width: `${Math.max(3, (s.amount / max) * 100)}%`, background: `linear-gradient(90deg, ${colors[i]}33, ${colors[i]})` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function CommandCenter() {
  const { data: d, error, loading, reload } = useAsync(() => api("/dashboard"));
  const { data: sc, reload: reloadSc } = useAsync(() => api<any[]>("/scenarios"));
  const [busy, setBusy] = useState<string | null>(null);
  const [split, setSplit] = useState(70);
  const [seed, setSeed] = useState(42);
  const [err2, setErr2] = useState<string | null>(null);

  const act = async (name: string, fn: () => Promise<any>) => {
    setBusy(name); setErr2(null);
    try { await fn(); await Promise.all([reload(), reloadSc()]); } catch (e: any) { setErr2(e.message); } finally { setBusy(null); }
  };

  if (loading && !d) return <Spinner label="Loading command center" />;
  if (error && !d) return <ErrorBox message={error} onRetry={reload} />;
  const m = d.metrics, ex = d.experiment, b = d.budget;

  return (
    <div className="space-y-6">
      <PageHeader title="Revenue Recovery Command Center" sub="RECLAIM OS · AI-governed recovery across failed payments, abandoned checkouts, subscriptions and invoices"
        right={<><SimTag /><button className="btn btn-ghost" disabled={busy === "reset"} onClick={() => act("reset", () => api("/simulator/reset", { method: "POST" }))}><RotateCcw className="h-4 w-4" />{busy === "reset" ? "Resetting…" : "Reset demo"}</button></>} />
      {err2 && <ErrorBox message={err2} />}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Metric label="Revenue at Risk" value={lakh(m.revenue_at_risk)} sub={`${inr(m.revenue_at_risk)} across ${d.funnel[0].cases} open cases`} tone="text-rose-300" />
        <Metric label="Recoverable" value={lakh(m.recoverable_revenue)} sub="Expected recovery of policy-permitted actions (estimated)" />
        <Metric label="Recovered" value={lakh(m.revenue_recovered)} sub="Observed in demo simulator" tone="text-emerald-300" />
        <Metric label="Incremental Recovery" value={lakh(m.incremental_recovery)} sub="Estimated vs control group (simulated)" accent />
      </div>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Metric label="Recovery Rate" value={pct(m.recovery_rate)} sub="Recovered ÷ revenue at risk" />
        <Metric label="Active Cases" value={m.active_cases} sub={`${m.total_cases} total`} />
        <Metric label="Human Escalations" value={m.human_escalations} sub={<a className="text-accent hover:underline" href="#/review">Open review queue →</a>} tone="text-amber-300" />
        <Metric label="Blocked Actions" value={m.blocked_actions} sub="Top-ranked action stopped by policy" tone="text-rose-300" />
      </div>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div><div className="label">Demo scenarios</div><div className="text-sm text-slate-400">Deterministic showcase cases for the 3-minute story</div></div>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(sc || []).map((s) => (
            <a key={s.key} href={`#/room/${s.case_id}`} className="group rounded-xl border border-white/[0.07] p-3.5 transition hover:border-accent/40 hover:bg-accent/[0.04]">
              <div className="flex items-start justify-between gap-2"><div className="text-sm font-medium text-slate-200 group-hover:text-white">{s.title}</div><Badge>{s.status}</Badge></div>
              <div className="mt-1 text-xs text-slate-500">{s.customer} · expected: <span className="text-slate-400">{s.expected}</span></div>
            </a>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1"><div className="label mb-4">Revenue recovery funnel</div><Funnel stages={d.funnel} /></Card>
        <Card className="xl:col-span-2">
          <div className="label mb-3">Recovery trend · last 14 days (simulated)</div>
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={d.recovery_trend}><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.cyan} stopOpacity={0.4} /><stop offset="100%" stopColor={C.cyan} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid stroke="rgba(255,255,255,.05)" vertical={false} /><XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} {...axis} /><YAxis tickFormatter={lakh} width={56} {...axis} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => inr(v)} /><Area type="monotone" dataKey="recovered" stroke={C.cyan} fill="url(#g)" strokeWidth={2} /></AreaChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <div className="label mb-3">Revenue at risk by source</div>
          <ResponsiveContainer width="100%" height={220}><BarChart data={d.risk_by_source}><CartesianGrid stroke="rgba(255,255,255,.05)" vertical={false} /><XAxis dataKey="source" tickFormatter={humanize} {...axis} /><YAxis tickFormatter={lakh} width={52} {...axis} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => inr(v)} /><Bar dataKey="amount" radius={[6, 6, 0, 0]}>{d.risk_by_source.map((_: any, i: number) => <Cell key={i} fill={[C.cyan, C.blue, C.teal, C.violet][i % 4]} />)}</Bar></BarChart></ResponsiveContainer>
        </Card>
        <Card>
          <div className="label mb-3">Recovered by action</div>
          <ResponsiveContainer width="100%" height={220}><BarChart data={d.recovery_by_action} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke="rgba(255,255,255,.05)" horizontal={false} /><XAxis type="number" tickFormatter={lakh} {...axis} /><YAxis type="category" dataKey="action" tickFormatter={humanize} width={120} {...axis} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => inr(v)} /><Bar dataKey="recovered" fill={C.teal} radius={[0, 6, 6, 0]} /></BarChart></ResponsiveContainer>
        </Card>
        <Card>
          <div className="label mb-3">Customer segments</div>
          <ResponsiveContainer width="100%" height={220}><BarChart data={d.segments}><CartesianGrid stroke="rgba(255,255,255,.05)" vertical={false} /><XAxis dataKey="segment" {...axis} /><YAxis tickFormatter={lakh} width={52} {...axis} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => inr(v)} /><Bar dataKey="at_risk" name="At risk" fill={C.blue} radius={[6, 6, 0, 0]} /><Bar dataKey="recovered" name="Recovered" fill={C.green} radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <div className="label mb-3">Top failure reasons (root causes)</div>
          <div className="space-y-2.5">
            {d.top_failure_reasons.slice(0, 6).map((r: any) => (
              <div key={r.reason}><div className="mb-1 flex justify-between gap-2 text-xs"><span className="truncate text-slate-300">{r.reason}</span><span className="num text-slate-500">{lakh(r.amount)} · {r.cases}</span></div>
                <div className="h-1.5 rounded bg-white/5"><div className="h-1.5 rounded bg-accent/70" style={{ width: `${(r.amount / d.top_failure_reasons[0].amount) * 100}%` }} /></div></div>
            ))}
          </div>
        </Card>
        <Card>
          <div className="label mb-3">Recovery budget utilization</div>
          <div className="num text-2xl text-white">{inr(b.allocated)} <span className="text-sm text-slate-500">of {inr(b.budget)} daily budget</span></div>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/5"><div className="h-3 rounded-full bg-gradient-to-r from-cyan-500 to-teal-300" style={{ width: `${Math.min(100, (b.allocated / b.budget) * 100)}%` }} /></div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><dt className="text-slate-500">Allocated (plan)</dt><dd className="num text-slate-200">{inr(b.allocated)}</dd></div><div><dt className="text-slate-500">Remaining</dt><dd className="num text-slate-200">{inr(b.remaining)}</dd></div>
            <div><dt className="text-slate-500">Expected recovery</dt><dd className="num text-emerald-300">{inr(b.expected_recovery)}</dd></div><div><dt className="text-slate-500">Pending opportunities</dt><dd className="num text-slate-200">{b.pending_opportunities}</dd></div></dl>
          <p className="mt-3 text-[11px] text-slate-600">Greedy allocation by expected value per rupee of intervention cost across cases awaiting action.</p>
        </Card>
        <Card>
          <div className="mb-3 flex items-center justify-between"><div className="label">AI vs Control</div><SimTag text="SIMULATED EXPERIMENT" /></div>
          {ex ? (<>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-cyan-400/[0.06] p-3"><div className="text-[11px] text-slate-500">AI group</div><div className="num text-xl text-cyan-300">{pct(ex.ai.rate_value)}</div><div className="num text-xs text-slate-500">{lakh(ex.ai.recovered)} · {ex.ai.cases} cases</div></div>
              <div className="rounded-xl bg-white/[0.04] p-3"><div className="text-[11px] text-slate-500">Control (no action)</div><div className="num text-xl text-slate-300">{pct(ex.control.rate_value)}</div><div className="num text-xs text-slate-500">{lakh(ex.control.recovered)} · {ex.control.cases} cases</div></div>
            </div>
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="flex justify-between"><span className="text-slate-500">Observed recovery (AI group)</span><span className="num text-slate-200">{inr(ex.observed_recovery)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Estimated incremental recovery</span><span className="num text-accent">{inr(ex.incremental_recovery)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Lift (case-rate, 95% CI)</span><span className="num text-slate-200">{ex.lift_pp.toFixed(1)}pp [{ex.ci95_pp[0].toFixed(1)}, {ex.ci95_pp[1].toFixed(1)}]</span></div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-600">{ex.note}</p>
          </>) : <div className="text-sm text-slate-500">No experiment yet.</div>}
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
            <label className="text-[11px] text-slate-500">AI share <input type="number" min={10} max={90} value={split} onChange={(e) => setSplit(+e.target.value)} className="ml-1 w-16 !py-1" />%</label>
            <label className="text-[11px] text-slate-500">seed <input type="number" min={0} value={seed} onChange={(e) => setSeed(+e.target.value)} className="ml-1 w-20 !py-1" /></label>
            <button className="btn btn-primary !py-1.5" disabled={busy === "exp"} onClick={() => act("exp", () => api("/experiments/run", { method: "POST", body: { split: split / 100, seed } }))}><Play className="h-3.5 w-3.5" />Run</button>
          </div>
        </Card>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-600"><FlaskConical className="h-3.5 w-3.5" />All figures are DEMO / SIMULATED. “Recovered” is observed in the local simulator; “incremental” is an estimate, not proof of causality.</div>
    </div>
  );
}
