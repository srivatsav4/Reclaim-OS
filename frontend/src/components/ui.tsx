import { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

export const C = { cyan: "#22D3EE", teal: "#2DD4BF", blue: "#3B82F6", amber: "#F59E0B", red: "#F43F5E", green: "#34D399", slate: "#64748B", violet: "#A78BFA" };
export const tooltipStyle = { background: "#0C1320", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, fontSize: 12, color: "#e2e8f0" };

export function Card({ children, className = "", pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <div className={`card ${pad ? "card-pad" : ""} ${className}`}>{children}</div>;
}

export function Metric({ label, value, sub, accent = false, tone }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean; tone?: string }) {
  return (
    <Card className={accent ? "border-accent/25 bg-gradient-to-b from-cyan-400/[0.07] to-transparent" : ""}>
      <div className="label">{label}</div>
      <div className={`num mt-2 text-3xl font-semibold tracking-tight ${tone || (accent ? "text-accent" : "text-white")}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

const BADGE: Record<string, string> = {
  ALLOW: "bg-emerald-400/10 text-emerald-300 border-emerald-400/25", ACT: "bg-emerald-400/10 text-emerald-300 border-emerald-400/25",
  BLOCK: "bg-rose-400/10 text-rose-300 border-rose-400/25", BLOCKED: "bg-rose-400/10 text-rose-300 border-rose-400/25",
  ESCALATE: "bg-amber-400/10 text-amber-300 border-amber-400/25", ESCALATED: "bg-amber-400/10 text-amber-300 border-amber-400/25",
  NO_ACTION: "bg-slate-400/10 text-slate-300 border-slate-400/25", RECOVERED: "bg-cyan-400/10 text-cyan-300 border-cyan-400/25",
  SUCCESS: "bg-emerald-400/10 text-emerald-300 border-emerald-400/25", FAILED: "bg-rose-400/10 text-rose-300 border-rose-400/25",
  CRITICAL: "bg-rose-400/10 text-rose-300 border-rose-400/25", HIGH: "bg-amber-400/10 text-amber-300 border-amber-400/25",
  MEDIUM: "bg-blue-400/10 text-blue-300 border-blue-400/25", LOW: "bg-slate-400/10 text-slate-400 border-slate-400/20",
  SIM: "bg-violet-400/10 text-violet-300 border-violet-400/25", DEMO: "bg-violet-400/10 text-violet-300 border-violet-400/25",
};
export function Badge({ children, kind }: { children: ReactNode; kind?: string }) {
  const k = kind || String(children);
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10.5px] font-semibold tracking-wide ${BADGE[k] || "bg-white/5 text-slate-300 border-white/10"}`}>{children}</span>;
}
export const SimTag = ({ text = "DEMO / SIMULATED" }: { text?: string }) => <Badge kind="SIM">{text}</Badge>;

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-10 justify-center text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />{label}…</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card flex items-start gap-3 border-rose-500/25 bg-rose-500/[0.05] p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
      <div className="flex-1"><div className="font-medium text-rose-200">Something went wrong</div><div className="text-slate-400">{message}</div></div>
      {onRetry && <button className="btn btn-ghost !py-1" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function PageHeader({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>{sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}</div>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">{children}</div>;
}
