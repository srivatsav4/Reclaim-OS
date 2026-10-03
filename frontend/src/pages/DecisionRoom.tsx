import { useEffect, useState } from "react";
import { CheckCircle2, FlaskConical, GitBranch, Play, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { api, useAsync } from "../api";
import { humanize, inr, shortTime } from "../format";
import { Badge, Card, Empty, ErrorBox, SimTag, Spinner } from "../components/ui";

const STATUS_FILTERS = [["ACTIVE", "Active"], ["ALL", "All"], ["RECOVERED", "Recovered"], ["BLOCKED", "Blocked"], ["NO_ACTION", "No action"]];

function Score({ score }: { score: number }) {
  const color = score >= 65 ? "#34D399" : score >= 40 ? "#22D3EE" : "#F59E0B";
  const r = 36, c = 2 * Math.PI * r;
  return (
    <svg width="96" height="96" viewBox="0 0 96 96"><circle cx="48" cy="48" r={r} fill="none" stroke="rgba(255,255,255,.07)" strokeWidth="8" />
      <circle cx="48" cy="48" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 48 48)" />
      <text x="48" y="54" textAnchor="middle" className="num" fill="white" fontSize="24" fontWeight="600">{score}</text></svg>
  );
}

export default function DecisionRoom({ caseId }: { caseId?: number }) {
  const [filter, setFilter] = useState("ACTIVE");
  const list = useAsync(() => api<any>(`/recovery-cases?limit=80&sort=amount${filter === "ALL" ? "" : `&status=${filter === "ACTIVE" ? "ANALYZED,ESCALATED,ATTEMPT_FAILED" : filter}`}`), [filter]);
  const [sel, setSel] = useState<number | undefined>(caseId);
  useEffect(() => { if (caseId) setSel(caseId); }, [caseId]);
  const items = list.data?.items || [];

  return (
    <div className="grid gap-5 xl:grid-cols-[340px_1fr]">
      <div>
        <div className="mb-3 flex items-center justify-between"><h1 className="text-xl font-semibold text-white">AI Decision Room</h1><SimTag /></div>
        <div className="mb-3 flex flex-wrap gap-1.5">{STATUS_FILTERS.map(([k, l]) => <button key={k} onClick={() => setFilter(k)} className={`rounded-lg px-2.5 py-1 text-xs ${filter === k ? "bg-accent/15 text-accent ring-1 ring-accent/30" : "text-slate-400 hover:bg-white/5"}`}>{l}</button>)}</div>
        {list.loading && !list.data ? <Spinner /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : (
          <div className="max-h-[calc(100vh-170px)] space-y-2 overflow-y-auto pr-1">
            {items.length === 0 && <Empty>No cases match this filter.</Empty>}
            {items.map((c: any) => (
              <button key={c.id} onClick={() => { setSel(c.id); window.history.replaceState(null, "", `#/room/${c.id}`); }}
                className={`w-full rounded-xl border p-3 text-left transition ${sel === c.id ? "border-accent/50 bg-accent/[0.06]" : "border-white/[0.07] hover:border-white/20"}`}>
                <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-slate-100">{c.customer_name}</span><span className="num text-sm text-white">{inr(c.revenue_at_risk)}</span></div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5"><Badge kind={c.priority}>{c.priority}</Badge><Badge kind={c.decision || undefined}>{c.decision || "NEW"}</Badge><span className="text-[11px] text-slate-500">{humanize(c.source_type)} · #{c.id}{c.scenario && !c.scenario.includes("GRAPH") ? " · ★ scenario" : ""}</span></div>
              </button>
            ))}
          </div>
        )}
      </div>
      {sel ? <CaseDetail key={sel} id={sel} onChanged={list.reload} /> : <Empty>Select a case, or open a scenario from the Command Center.</Empty>}
    </div>
  );
}

function CaseDetail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { data: c, error, loading, reload } = useAsync(() => api<any>(`/recovery-cases/${id}`), [id]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  if (loading && !c) return <Spinner />;
  if (error || !c) return <ErrorBox message={error || "Case not found"} onRetry={reload} />;
  const a = c.analysis;
  const closed = ["RECOVERED", "STOPPED", "CONTROL_HOLD", "CONTROL_RECOVERED", "CLOSED_RESOLVED", "CLOSED_NO_ACTION", "REJECTED"].includes(c.status);
  const call = async (path: string) => {
    setBusy(true); setErr(null);
    try { const r = await api(`/recovery-cases/${id}/${path}`, { method: "POST" }); if (path === "execute") setResult(r); await reload(); onChanged(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const sel = a.candidates.find((x: any) => x.action === a.selected_action);

  return (
    <div className="space-y-4 fade-in">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2"><h2 className="text-xl font-semibold text-white">{c.customer_name}</h2><Badge kind={c.priority}>{c.priority}</Badge><Badge>{c.status}</Badge></div>
            <div className="mt-1 text-sm text-slate-500">{humanize(c.source_type)} #{c.source_id} · case #{c.id} · {c.segment} · group {c.group || "—"}</div>
            <div className="mt-3 flex gap-4"><div><div className="label">Revenue at risk</div><div className="num text-3xl font-semibold text-rose-300">{inr(c.revenue_at_risk)}</div></div>
              {c.actual_recovery > 0 && <div><div className="label">Recovered (simulated)</div><div className="num text-3xl font-semibold text-emerald-300">{inr(c.actual_recovery)}</div></div>}</div>
          </div>
          <div className="flex items-center gap-4"><div className="text-center"><Score score={a.score} /><div className="label -mt-1">Recoverability</div></div></div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <a className="btn btn-ghost !py-1.5" href={`#/graph/${c.customer_id}`}><GitBranch className="h-4 w-4" />Risk graph</a>
          <a className="btn btn-ghost !py-1.5" href={`#/lab/${c.id}`}><FlaskConical className="h-4 w-4" />Recovery Lab</a>
          <a className="btn btn-ghost !py-1.5" href={`#/audit/${c.id}`}>Audit trail</a>
          <button className="btn btn-ghost !py-1.5" disabled={busy || closed} onClick={() => call("analyze")}><RefreshCw className="h-4 w-4" />Re-analyze</button>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="label mb-2">Why this case?</div>
          <div className="text-sm text-slate-300">Root cause: <span className="font-medium text-white">{a.root_cause}</span></div>
          <ul className="mt-2 space-y-1 text-sm text-slate-400">{a.evidence.map((e: string) => <li key={e}>• {e}</li>)}</ul>
          <div className="label mb-2 mt-4">Recoverability breakdown</div>
          <div className="num space-y-1 text-xs">{a.score_reasons.map((r: any, i: number) => <div key={i} className="flex justify-between gap-3"><span className="text-slate-400">{r.text}</span><span className={r.points > 0 ? "text-emerald-300" : "text-rose-300"}>{r.points > 0 ? "+" : ""}{r.points}</span></div>)}</div>
        </Card>
        <Card className={a.decision === "ACT" ? "border-emerald-400/20" : a.decision === "ESCALATE" ? "border-amber-400/25" : "border-slate-400/20"}>
          <div className="label mb-2">Decision</div>
          <div className="flex items-center gap-2 text-2xl font-semibold text-white">{a.decision === "NO_ACTION" ? "NO ACTION" : humanize(a.selected_action).toUpperCase()}<Badge kind={a.decision}>{a.decision === "ACT" ? "PERMITTED" : a.decision}</Badge></div>
          <div className="mt-3 text-sm font-medium text-slate-300">{a.decision === "NO_ACTION" ? "Reason" : "Why this action?"}</div>
          <ul className="mt-1 space-y-1 text-sm text-slate-400">{a.explanation.why_action.map((w: string) => <li key={w}>• {w}</li>)}</ul>
          <div className="mt-3 text-sm font-medium text-slate-300">Stopping condition</div><p className="text-sm text-slate-500">{a.explanation.stopping_condition}</p>
          {a.blocked_top && <div className="mt-3 flex gap-2 rounded-lg border border-rose-500/25 bg-rose-500/[0.06] p-2.5 text-xs text-rose-200"><ShieldAlert className="h-4 w-4 shrink-0" /><div><b>{humanize(a.blocked_top.action)}</b> ranked highest but was blocked: {a.blocked_top.policy_reasons[0]}</div></div>}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {a.decision === "ESCALATE" && !closed ? <a href="#/review" className="btn btn-primary"><ShieldAlert className="h-4 w-4" />Needs human approval → Review queue</a>
              : <button className="btn btn-primary" disabled={busy || closed} onClick={() => call("execute")}><Play className="h-4 w-4" />{busy ? "Executing…" : a.decision === "NO_ACTION" ? "Confirm no action" : "EXECUTE"}</button>}
            {closed && <span className="text-xs text-slate-500">Case closed ({c.status}).</span>}
          </div>
          {err && <div className="mt-3 text-sm text-rose-300">{err}</div>}
          {result && (
            <div className={`mt-3 flex items-start gap-2 rounded-xl border p-3 text-sm ${result.result === "SUCCESS" ? "border-emerald-400/30 bg-emerald-400/[0.07] text-emerald-200" : result.result === "NO_ACTION" ? "border-slate-400/30 bg-white/5 text-slate-200" : "border-rose-400/30 bg-rose-400/[0.07] text-rose-200"}`}>
              {result.result === "SUCCESS" ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
              <div><div className="font-semibold">{result.result === "SUCCESS" ? `SUCCESS · ${inr(result.amount_recovered)} recovered (simulated)` : result.result}</div><div className="text-xs opacity-80">{result.message}</div></div>
            </div>
          )}
        </Card>
      </div>

      <Card pad={false}>
        <div className="flex items-center justify-between p-5 pb-3"><div className="label">Candidate actions · expected-value optimizer</div><SimTag text="ESTIMATED" /></div>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="border-y border-white/[0.06] text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="px-5 py-2">Action</th><th>Prob.</th><th>Expected recovery</th><th>Cost</th><th>Friction</th><th>Expected value</th><th className="pr-5">Policy</th></tr></thead>
          <tbody>{[...a.candidates].sort((x: any, y: any) => y.expected_value - x.expected_value).map((x: any) => (
            <tr key={x.action} className={`border-b border-white/[0.04] ${x.action === a.selected_action ? "bg-accent/[0.07]" : ""}`}>
              <td className="px-5 py-2.5 font-medium text-slate-200">{humanize(x.action)}{x.action === a.selected_action && <span className="ml-2 text-[10px] font-bold text-accent">SELECTED</span>}</td>
              <td className="num text-slate-400">{(x.probability * 100).toFixed(0)}%</td><td className="num text-slate-300">{inr(x.expected_recovery)}</td><td className="num text-slate-400">{inr(x.cost)}</td>
              <td className="text-slate-400">{x.friction} <span className="num text-xs text-slate-600">(-{inr(x.friction_penalty)})</span></td><td className="num font-medium text-white">{inr(x.expected_value)}</td>
              <td className="pr-5" title={x.policy_reasons.join("; ")}><Badge kind={x.policy_status}>{x.policy_status}</Badge></td></tr>))}</tbody>
        </table></div>
        <p className="p-5 pt-3 text-[11px] text-slate-600">expected value = revenue at risk × probability − intervention cost − friction penalty. The highest-value <i>permitted</i> action wins; hover a policy badge for the reason.{sel && sel.policy_status === "ESCALATE" ? " Selected action requires human approval." : ""}</p>
      </Card>

      <Card>
        <div className="label mb-3">Audit timeline</div>
        <ol className="relative space-y-2.5 border-l border-white/10 pl-5">{c.audit.map((e: any) => (
          <li key={e.id} className="relative"><span className="absolute -left-[25px] top-1.5 h-2 w-2 rounded-full bg-accent" />
            <div className="flex flex-wrap items-baseline gap-2 text-xs"><span className="font-mono font-semibold text-slate-200">{e.event_type}</span>{e.outcome && <Badge kind={e.outcome}>{e.outcome}</Badge>}<span className="text-slate-600">{e.actor} · {shortTime(e.timestamp)}</span></div>
            <div className="text-xs text-slate-500">{e.reason}</div></li>))}</ol>
      </Card>
    </div>
  );
}
