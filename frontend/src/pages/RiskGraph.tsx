import { useState } from "react";
import { api, useAsync } from "../api";
import { humanize, inr } from "../format";
import { Badge, Card, Empty, ErrorBox, PageHeader, SimTag, Spinner } from "../components/ui";

const TYPES = ["checkout", "payment", "subscription", "invoice"];
const STATE: Record<string, [string, string]> = { // case status -> [label, colour]
  RECOVERED: ["RECOVERED", "#34D399"], CLOSED_RESOLVED: ["RESOLVED", "#34D399"], ESCALATED: ["ESCALATED", "#F59E0B"],
  BLOCKED: ["BLOCKED", "#F43F5E"], STOPPED: ["STOPPED", "#F43F5E"], ATTEMPT_FAILED: ["RETRYING", "#F59E0B"], NO_ACTION: ["NO ACTION", "#64748B"],
};
const ROOT_LABEL: Record<string, string> = { checkout: "ABANDONED", payment: "FAILED", subscription: "PAST DUE", invoice: "OVERDUE" };

function Graph({ g }: { g: any }) {
  const W = 760, H = 460, cx = 130, cy = H / 2;
  const nodes = TYPES.flatMap((t) => g.nodes.filter((n: any) => n.type === t).slice(0, 2));
  const ys = (i: number) => 50 + (i * (H - 100)) / Math.max(1, nodes.length - 1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <defs><radialGradient id="cg"><stop offset="0%" stopColor="#22D3EE" stopOpacity=".35" /><stop offset="100%" stopColor="#22D3EE" stopOpacity="0" /></radialGradient></defs>
      <circle cx={cx} cy={cy} r="95" fill="url(#cg)" />
      {nodes.map((n: any, i: number) => {
        const y = ys(i), [lab, col] = STATE[n.case_status] || [ROOT_LABEL[n.type], "#F43F5E"];
        return (
          <g key={n.case_id}>
            <path d={`M ${cx + 46} ${cy} C ${cx + 150} ${cy}, ${cx + 150} ${y}, 330 ${y}`} fill="none" stroke={col} strokeOpacity=".5" strokeWidth="1.5" strokeDasharray={n.exposure ? "0" : "4 4"} />
            <a href={`#/room/${n.case_id}`} style={{ cursor: "pointer" }}>
              <rect x="330" y={y - 30} width="400" height="60" rx="14" fill="#0C1320" stroke={col} strokeOpacity=".55" />
              <text x="350" y={y - 8} fill="#94a3b8" fontSize="11" letterSpacing="1.5">{n.type.toUpperCase()} · CASE #{n.case_id}</text>
              <text x="350" y={y + 14} fill="white" fontSize="17" fontWeight="600" className="num">{inr(n.amount)}</text>
              <rect x="560" y={y - 11} width="154" height="22" rx="7" fill={col} fillOpacity=".14" stroke={col} strokeOpacity=".4" />
              <text x="637" y={y + 4} fill={col} fontSize="10.5" fontWeight="700" textAnchor="middle" letterSpacing="1">{ROOT_LABEL[n.type]} → {lab}</text>
            </a>
          </g>
        );
      })}
      <circle cx={cx} cy={cy} r="46" fill="#0C1320" stroke="#22D3EE" strokeWidth="2" />
      <text x={cx} y={cy - 4} textAnchor="middle" fill="white" fontSize="11" fontWeight="600" letterSpacing="2">CUSTOMER</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#22D3EE" fontSize="12" className="num">{g.customer.name.split(" ")[0]}</text>
    </svg>
  );
}

export default function RiskGraph({ customerId }: { customerId?: number }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number>(customerId || 1);
  const list = useAsync(() => api<any>(`/customers?at_risk_only=true&limit=60${q ? `&q=${encodeURIComponent(q)}` : ""}`), [q]);
  const g = useAsync(() => api<any>(`/customers/${sel}`), [sel]);
  const multi = (list.data?.items || []);

  return (
    <div>
      <PageHeader title="Revenue Risk Graph" sub="One customer, every revenue leak: unified exposure across checkout, payment, subscription and invoice" right={<SimTag />} />
      <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
        <div>
          <input className="mb-3 w-full" placeholder="Search customers with cases…" value={q} onChange={(e) => setQ(e.target.value)} />
          {list.loading && !list.data ? <Spinner /> : list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : (
            <div className="max-h-[calc(100vh-240px)] space-y-2 overflow-y-auto pr-1">
              {multi.length === 0 && <Empty>No customers found.</Empty>}
              {multi.map((c: any) => (
                <button key={c.id} onClick={() => { setSel(c.id); window.history.replaceState(null, "", `#/graph/${c.id}`); }} className={`w-full rounded-xl border p-3 text-left ${sel === c.id ? "border-accent/50 bg-accent/[0.06]" : "border-white/[0.07] hover:border-white/20"}`}>
                  <div className="flex justify-between gap-2"><span className="truncate text-sm font-medium">{c.name}</span><span className="num text-sm text-rose-300">{inr(c.exposure)}</span></div>
                  <div className="mt-1 text-[11px] text-slate-500">{c.segment} · LTV {inr(c.lifetime_value)}</div>
                </button>))}
            </div>)}
        </div>
        <div>
          {g.loading && !g.data ? <Spinner /> : g.error || !g.data ? <ErrorBox message={g.error || "Not found"} onRetry={g.reload} /> : (
            <div className="space-y-4 fade-in">
              <Card>
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div><h2 className="text-xl font-semibold text-white">{g.data.customer.name}</h2><div className="text-sm text-slate-500">{g.data.customer.segment} · {g.data.customer.email} · {g.data.customer.contact_allowed ? "contact allowed" : "contact NOT allowed"}</div></div>
                  <div className="text-right"><div className="label">Total exposure</div><div className="num text-4xl font-semibold text-rose-300">{inr(g.data.total_exposure)}</div></div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {TYPES.map((t) => <div key={t} className="rounded-xl bg-white/[0.04] p-3"><div className="label">{humanize(t)}</div><div className="num text-lg text-white">{inr(g.data.by_source[t] || 0)}</div></div>)}
                </div>
              </Card>
              <Card><Graph g={g.data} /><p className="text-[11px] text-slate-600">Click a node to open its case in the AI Decision Room. Dashed link = already resolved (no exposure). Showing up to two cases per source.</p></Card>
              <div className="flex flex-wrap gap-2 text-xs text-slate-500">{g.data.nodes.map((n: any) => <Badge key={n.case_id} kind={n.decision || undefined}>{humanize(n.type)}: {n.decision}</Badge>)}</div>
            </div>)}
        </div>
      </div>
    </div>
  );
}
