import { useEffect, useState } from "react";
import { FlaskConical, Play } from "lucide-react";
import { api, useAsync } from "../api";
import { humanize, inr } from "../format";
import { Badge, Card, ErrorBox, PageHeader, SimTag, Spinner } from "../components/ui";

const STRATS = [["OPTIMIZER", "AI optimizer (policy-bounded)"], ["RETRY_ONLY", "Retry everything"], ["BLANKET_OUTREACH", "Blanket outreach"], ["DO_NOTHING", "Do nothing"]];
const SEGS = ["ALL", "Consumer", "SMB", "Mid-Market", "Enterprise"];

export default function RecoveryLab({ caseId }: { caseId?: number }) {
  const [p, setP] = useState({ budget: 10000, segment: "ALL", strategy: "OPTIMIZER", retry_delay_hours: 48, contact_frequency: 2 });
  const [res, setRes] = useState<any>(null);
  const [cmp, setCmp] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); setErr(null); try { setRes(await api("/recovery-lab/simulate", { method: "POST", body: p })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  const compare = async () => {
    setBusy(true); setErr(null);
    try { setCmp(await Promise.all(STRATS.map(([s]) => api("/recovery-lab/simulate", { method: "POST", body: { ...p, strategy: s } })))); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  useEffect(() => { run(); /* eslint-disable-next-line */ }, []);
  const set = (k: string, v: any) => setP((o) => ({ ...o, [k]: v }));

  return (
    <div className="space-y-6">
      <PageHeader title="Recovery Lab" sub="Counterfactual what-ifs. Everything here is SIMULATION, never actual recovery." right={<SimTag text="SIMULATION" />} />
      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <Card>
          <div className="label mb-4">Campaign inputs</div>
          <div className="space-y-4 text-sm">
            <label className="block"><span className="text-slate-400">Recovery budget (₹)</span><input type="number" min={0} className="mt-1 w-full num" value={p.budget} onChange={(e) => set("budget", Math.max(0, +e.target.value))} /></label>
            <label className="block"><span className="text-slate-400">Customer segment</span><select className="mt-1 w-full" value={p.segment} onChange={(e) => set("segment", e.target.value)}>{SEGS.map((s) => <option key={s}>{s}</option>)}</select></label>
            <label className="block"><span className="text-slate-400">Recovery strategy</span><select className="mt-1 w-full" value={p.strategy} onChange={(e) => set("strategy", e.target.value)}>{STRATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label className="block"><span className="text-slate-400">Retry delay: <b className="num text-white">{p.retry_delay_hours}h</b></span><input type="range" min={0} max={168} step={6} className="mt-1 w-full" value={p.retry_delay_hours} onChange={(e) => set("retry_delay_hours", +e.target.value)} /></label>
            <label className="block"><span className="text-slate-400">Contact frequency: <b className="num text-white">{p.contact_frequency} messages</b> <span className="text-slate-600">(policy max 3)</span></span><input type="range" min={1} max={7} className="mt-1 w-full" value={p.contact_frequency} onChange={(e) => set("contact_frequency", +e.target.value)} /></label>
            <div className="flex gap-2"><button className="btn btn-primary flex-1" disabled={busy} onClick={run}><Play className="h-4 w-4" />Simulate</button><button className="btn btn-ghost" disabled={busy} onClick={compare}>Compare all</button></div>
          </div>
        </Card>
        <div className="space-y-4">
          {err && <ErrorBox message={err} />}
          {!res ? <Spinner label="Simulating" /> : (
            <Card className="border-violet-400/20">
              <div className="mb-4 flex items-center justify-between"><div className="label">Projected outcome · {humanize(res.strategy)}</div><SimTag text="SIMULATION · NOT ACTUAL RECOVERY" /></div>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div><div className="label">Expected recovery</div><div className="num text-2xl text-emerald-300">{inr(res.expected_recovery)}</div></div>
                <div><div className="label">Estimated cost</div><div className="num text-2xl text-white">{inr(res.estimated_cost)}</div></div>
                <div><div className="label">Expected ROI</div><div className="num text-2xl text-accent">{res.expected_roi === null ? "—" : `${res.expected_roi.toFixed(1)}×`}</div></div>
                <div><div className="label">Policy violations</div><div className={`num text-2xl ${res.policy_violations ? "text-rose-300" : "text-emerald-300"}`}>{res.policy_violations}</div></div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4 border-t border-white/[0.06] pt-4 text-sm lg:grid-cols-4">
                <div><div className="text-slate-500">Projected recoveries</div><div className="num text-slate-200">{res.projected_recoveries} of {res.cases_targeted} cases</div></div>
                <div><div className="text-slate-500">Budget used</div><div className="num text-slate-200">{inr(res.allocated)} / {inr(res.budget)}</div></div>
                <div><div className="text-slate-500">Remaining</div><div className="num text-slate-200">{inr(res.remaining)}</div></div>
                <div><div className="text-slate-500">Effective contact freq.</div><div className="num text-slate-200">{res.effective_contact_frequency}{res.effective_contact_frequency !== p.contact_frequency && <span className="text-amber-300"> (clamped by policy)</span>}</div></div>
              </div>
            </Card>)}
          {cmp && (
            <Card pad={false}><div className="p-5 pb-2 label">Strategy comparison (same budget, segment and settings)</div>
              <table className="w-full text-sm"><thead><tr className="border-y border-white/[0.06] text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="px-5 py-2">Strategy</th><th>Expected recovery</th><th>Cost</th><th>ROI</th><th className="pr-5">Violations</th></tr></thead>
                <tbody>{cmp.map((r) => <tr key={r.strategy} className="border-b border-white/[0.04]"><td className="px-5 py-2.5">{humanize(r.strategy)}</td><td className="num">{inr(r.expected_recovery)}</td><td className="num text-slate-400">{inr(r.estimated_cost)}</td><td className="num text-accent">{r.expected_roi === null ? "—" : `${r.expected_roi.toFixed(1)}×`}</td><td className={`num pr-5 ${r.policy_violations ? "text-rose-300" : "text-emerald-300"}`}>{r.policy_violations}</td></tr>)}</tbody></table>
            </Card>)}
        </div>
      </div>
      <CaseLab initial={caseId} />
    </div>
  );
}

function CaseLab({ initial }: { initial?: number }) {
  const sc = useAsync(() => api<any[]>("/scenarios"));
  const [id, setId] = useState<number | undefined>(initial);
  useEffect(() => { if (!id && sc.data?.length) setId(sc.data.find((s) => s.key === "S2_LINK_SUCCESS")?.case_id || sc.data[0].case_id); }, [sc.data, id]);
  const lab = useAsync(() => (id ? api<any>(`/recovery-lab/${id}`) : Promise.resolve(null)), [id]);
  const max = Math.max(1, ...(lab.data?.candidates || []).map((c: any) => c.expected_recovery));
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div><div className="label">Case counterfactuals</div><div className="text-sm text-slate-500">What each action is estimated to recover for one case</div></div>
        <select value={id ?? ""} onChange={(e) => setId(+e.target.value)}>{(sc.data || []).map((s) => <option key={s.case_id} value={s.case_id}>{s.title}</option>)}</select>
      </div>
      {lab.loading && !lab.data ? <Spinner /> : lab.error ? <ErrorBox message={lab.error} onRetry={lab.reload} /> : lab.data && (
        <div className="space-y-2.5">
          {lab.data.candidates.map((c: any) => (
            <div key={c.action}>
              <div className="mb-1 flex items-center justify-between text-sm"><span className={c.selected ? "font-semibold text-accent" : "text-slate-300"}>{humanize(c.action)} {c.selected && <Badge kind="ACT">SELECTED ACTION</Badge>} <Badge kind={c.policy_status}>{c.policy_status}</Badge></span>
                <span className="num text-slate-300"><span className="mr-2 text-[10px] font-bold text-violet-300">ESTIMATED</span>{inr(c.expected_recovery)}</span></div>
              <div className="h-2.5 rounded bg-white/5"><div className={`h-2.5 rounded ${c.selected ? "bg-accent" : c.policy_status === "BLOCK" ? "bg-rose-400/40" : "bg-slate-500/60"}`} style={{ width: `${Math.max(1.5, (c.expected_recovery / max) * 100)}%` }} /></div>
            </div>))}
          <div className="mt-4 rounded-xl border border-white/[0.07] p-3 text-sm">
            <span className="label">Actual outcome</span>{" "}
            {lab.data.actual.length ? lab.data.actual.map((a: any, i: number) => <span key={i} className="ml-2"><Badge kind={a.result}>{a.result}</Badge> <span className="num text-slate-300">{inr(a.amount_recovered)}</span></span>) : <span className="ml-2 text-slate-500">Not executed yet. Figures above are estimates only.</span>}
          </div>
        </div>)}
      <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-600"><FlaskConical className="h-3.5 w-3.5" />Estimated outcomes are model expectations, not realised results.</div>
    </Card>
  );
}
