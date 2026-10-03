import { useState } from "react";
import { api, useAsync } from "../api";
import { shortTime } from "../format";
import { Badge, Card, Empty, ErrorBox, PageHeader, SimTag, Spinner } from "../components/ui";

const EVENTS = ["CASE_CREATED", "RISK_CALCULATED", "ROOT_CAUSE_IDENTIFIED", "ACTION_RECOMMENDED", "POLICY_CHECKED", "ACTION_ALLOWED", "ACTION_BLOCKED", "ACTION_EXECUTED", "PAYMENT_SUCCEEDED", "PAYMENT_FAILED", "HUMAN_ESCALATED", "HUMAN_APPROVED", "HUMAN_REJECTED", "HUMAN_INFO_REQUESTED", "CASE_RESOLVED", "NO_ACTION_SELECTED", "EXPERIMENT_RUN"];
const ACTORS = ["RECLAIM_AGENT", "POLICY_GATE", "SIMULATOR", "INGESTION", "EXPERIMENT_ENGINE", "demo_reviewer"];
const OUTCOMES = ["ALLOW", "BLOCK", "ESCALATE", "SUCCESS", "FAILED", "APPROVED", "REJECTED", "NO_ACTION", "STOPPED"];
const DOT: Record<string, string> = { ACTION_BLOCKED: "bg-rose-400", PAYMENT_FAILED: "bg-rose-400", HUMAN_REJECTED: "bg-rose-400", PAYMENT_SUCCEEDED: "bg-emerald-400", HUMAN_APPROVED: "bg-emerald-400", CASE_RESOLVED: "bg-emerald-400", HUMAN_ESCALATED: "bg-amber-400", POLICY_CHECKED: "bg-blue-400", NO_ACTION_SELECTED: "bg-slate-400", ACTION_EXECUTED: "bg-accent" };

export default function Audit({ initialCase }: { initialCase?: number }) {
  const [f, setF] = useState({ case_id: initialCase ? String(initialCase) : "", customer_id: "", event_type: "", actor: "", policy: "", outcome: "", date_from: "", date_to: "" });
  const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  const { data, error, loading, reload } = useAsync(() => api<any>(`/audit?limit=200&${qs}`), [qs]);
  const set = (k: string, v: string) => setF((o) => ({ ...o, [k]: v }));
  const sel = (k: string, opts: string[], ph: string) => <select value={(f as any)[k]} onChange={(e) => set(k, e.target.value)}><option value="">{ph}</option>{opts.map((o) => <option key={o}>{o}</option>)}</select>;

  return (
    <div>
      <PageHeader title="Audit Ledger" sub="Every decision, policy check and outcome, in order" right={<SimTag />} />
      <Card className="mb-4">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <input placeholder="Case ID" inputMode="numeric" value={f.case_id} onChange={(e) => set("case_id", e.target.value.replace(/\D/g, ""))} />
          <input placeholder="Customer ID" inputMode="numeric" value={f.customer_id} onChange={(e) => set("customer_id", e.target.value.replace(/\D/g, ""))} />
          {sel("event_type", EVENTS, "Any action / event")}{sel("actor", ACTORS, "Any agent / actor")}
          <input placeholder="Policy (e.g. HUMAN_APPROVAL)" value={f.policy} onChange={(e) => set("policy", e.target.value)} />
          {sel("outcome", OUTCOMES, "Any outcome")}
          <input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} title="From" />
          <input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value ? e.target.value + "T23:59:59" : "")} title="To" />
        </div>
        <button className="btn btn-ghost mt-3 !py-1" onClick={() => setF({ case_id: "", customer_id: "", event_type: "", actor: "", policy: "", outcome: "", date_from: "", date_to: "" })}>Clear filters</button>
      </Card>
      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data || data.items.length === 0 ? <Empty>No audit events match these filters.</Empty> : (
        <Card>
          <div className="mb-3 text-xs text-slate-500">Showing {data.items.length} of {data.total} events (newest first)</div>
          <ol className="relative space-y-3 border-l border-white/10 pl-6">
            {data.items.map((e: any) => (
              <li key={e.id} className="relative">
                <span className={`absolute -left-[29px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-ink-950 ${DOT[e.event_type] || "bg-slate-500"}`} />
                <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold text-slate-100">{e.event_type}</span>{e.outcome && <Badge kind={e.outcome}>{e.outcome}</Badge>}
                  {e.case_id && <a href={`#/room/${e.case_id}`} className="text-xs text-accent hover:underline">case #{e.case_id}</a>}{e.customer_id && <span className="text-xs text-slate-600">cust #{e.customer_id}</span>}
                  <span className="ml-auto text-[11px] text-slate-600">{e.actor} · {shortTime(e.timestamp)}</span></div>
                <div className="text-sm text-slate-400">{e.reason}</div>
                {e.policy && <div className="font-mono text-[11px] text-amber-300/80">policy: {e.policy}</div>}
              </li>))}
          </ol>
        </Card>)}
    </div>
  );
}
