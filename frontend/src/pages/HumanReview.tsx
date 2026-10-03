import { useState } from "react";
import { Check, Eye, HelpCircle, X } from "lucide-react";
import { api, useAsync } from "../api";
import { humanize, inr, shortTime } from "../format";
import { Badge, Card, Empty, ErrorBox, PageHeader, SimTag, Spinner } from "../components/ui";

const TABS = [["pending", "Pending reviews"], ["high", "High-value cases"], ["policy", "Policy exceptions"], ["escalated", "Escalated (all open)"], ["decided", "Decided"]] as const;

export default function HumanReview() {
  const { data, error, loading, reload } = useAsync(() => api<any>("/reviews"));
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("pending");
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const act = async (r: any, kind: "approve" | "reject" | "request-info") => {
    setBusy(r.case_id); setMsg(null);
    try {
      const out = await api<any>(`/recovery-cases/${r.case_id}/${kind}`, { method: "POST", body: { by: "demo_reviewer", note: kind === "request-info" ? "More information requested from account owner" : undefined } });
      setMsg({ ok: true, text: kind === "approve" ? `Approved case #${r.case_id}: simulated outcome ${out.result}${out.amount_recovered ? ` (${inr(out.amount_recovered)} recovered)` : ""}` : kind === "reject" ? `Rejected case #${r.case_id}; case closed.` : `Requested more information on case #${r.case_id}.` });
      await reload();
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(null); }
  };

  const all: any[] = data?.items || [];
  const open = all.filter((r) => ["PENDING", "INFO_REQUESTED"].includes(r.status));
  const view = tab === "pending" ? open.filter((r) => r.status === "PENDING") : tab === "high" ? open.filter((r) => r.high_value) : tab === "policy" ? open.filter((r) => r.policy_conflict) : tab === "escalated" ? open : all.filter((r) => !["PENDING", "INFO_REQUESTED"].includes(r.status));

  return (
    <div>
      <PageHeader title="Human Review" sub="Cases the policy gate will not let the agent execute alone" right={<SimTag />} />
      <div className="mb-4 flex flex-wrap gap-1.5">{TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-lg px-3 py-1.5 text-sm ${tab === k ? "bg-accent/15 text-accent ring-1 ring-accent/30" : "text-slate-400 hover:bg-white/5"}`}>{l}{k === "pending" && <span className="num ml-1.5 text-xs opacity-70">{open.filter((r) => r.status === "PENDING").length}</span>}</button>)}</div>
      {msg && <div className={`mb-4 rounded-xl border p-3 text-sm ${msg.ok ? "border-emerald-400/30 bg-emerald-400/[0.07] text-emerald-200" : "border-rose-400/30 bg-rose-400/[0.07] text-rose-200"}`}>{msg.text}</div>}
      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : view.length === 0 ? <Empty>Nothing here. {tab === "pending" ? "All escalations are handled." : ""}</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {view.map((r) => {
            const isOpen = ["PENDING", "INFO_REQUESTED"].includes(r.status);
            return (
              <Card key={r.id} className="fade-in">
                <div className="flex items-start justify-between gap-3">
                  <div><div className="text-lg font-semibold text-white">{r.customer}</div><div className="text-xs text-slate-500">case #{r.case_id} · {shortTime(r.created_at)}</div></div>
                  <div className="text-right"><div className="num text-2xl font-semibold text-rose-300">{inr(r.amount)}</div><div className="mt-1 flex justify-end gap-1.5"><Badge kind={r.risk}>{r.risk}</Badge><Badge kind={r.status === "APPROVED" ? "SUCCESS" : r.status === "REJECTED" ? "BLOCK" : "ESCALATE"}>{r.status}</Badge></div></div>
                </div>
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex gap-3"><dt className="w-28 shrink-0 text-slate-500">AI recommendation</dt><dd className="text-slate-200">{humanize(r.recommended_action || "")} <span className="text-slate-500">(expected {inr(r.expected_recovery)})</span></dd></div>
                  <div className="flex gap-3"><dt className="w-28 shrink-0 text-slate-500">Reason</dt><dd className="text-slate-300">{r.reason}</dd></div>
                  <div className="flex gap-3"><dt className="w-28 shrink-0 text-slate-500">Policy</dt><dd className="font-mono text-xs text-amber-300">{r.policy_conflict || "—"}</dd></div>
                  <div className="flex gap-3"><dt className="w-28 shrink-0 text-slate-500">Next step</dt><dd className="text-slate-300">{r.recommended_step}</dd></div>
                  <div className="flex gap-3"><dt className="w-28 shrink-0 text-slate-500">Root cause</dt><dd className="text-slate-400">{r.root_cause}</dd></div>
                </dl>
                <div className="mt-4 flex flex-wrap gap-2">
                  {isOpen ? (<>
                    <button className="btn btn-primary !py-1.5" disabled={busy === r.case_id} onClick={() => act(r, "approve")}><Check className="h-4 w-4" />Approve</button>
                    <button className="btn btn-danger !py-1.5" disabled={busy === r.case_id} onClick={() => act(r, "reject")}><X className="h-4 w-4" />Reject</button>
                    <button className="btn btn-ghost !py-1.5" disabled={busy === r.case_id || r.status === "INFO_REQUESTED"} onClick={() => act(r, "request-info")}><HelpCircle className="h-4 w-4" />{r.status === "INFO_REQUESTED" ? "Info requested" : "Request more info"}</button>
                  </>) : <span className="text-xs text-slate-500">Decided by {r.decided_by}{r.note ? ` · ${r.note}` : ""}</span>}
                  <a className="btn btn-ghost !py-1.5" href={`#/room/${r.case_id}`}><Eye className="h-4 w-4" />Inspect</a>
                </div>
              </Card>);
          })}
        </div>)}
    </div>
  );
}
