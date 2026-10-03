import { useEffect, useState } from "react";
import { Activity, FlaskConical, GitBranch, Gauge, ScrollText, ShieldCheck, Users } from "lucide-react";
import Landing from "./pages/Landing";
import CommandCenter from "./pages/CommandCenter";
import DecisionRoom from "./pages/DecisionRoom";
import RiskGraph from "./pages/RiskGraph";
import RecoveryLab from "./pages/RecoveryLab";
import HumanReview from "./pages/HumanReview";
import Audit from "./pages/Audit";
import { SimTag } from "./components/ui";

function useHash() {
  const [h, setH] = useState(window.location.hash || "#/");
  useEffect(() => { const f = () => setH(window.location.hash || "#/"); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return h.replace(/^#/, "") || "/";
}

const NAV = [
  { to: "/command", label: "Command Center", icon: Gauge },
  { to: "/room", label: "AI Decision Room", icon: Activity },
  { to: "/graph", label: "Revenue Risk Graph", icon: GitBranch },
  { to: "/lab", label: "Recovery Lab", icon: FlaskConical },
  { to: "/review", label: "Human Review", icon: Users },
  { to: "/audit", label: "Audit Ledger", icon: ScrollText },
];

export default function App() {
  const path = useHash();
  const [, seg, arg] = path.split("/");
  if (path === "/" || path === "") return <Landing />;
  const id = arg ? Number(arg) : undefined;
  let page = <CommandCenter />;
  if (seg === "room") page = <DecisionRoom caseId={id} />;
  else if (seg === "graph") page = <RiskGraph customerId={id} />;
  else if (seg === "lab") page = <RecoveryLab caseId={id} />;
  else if (seg === "review") page = <HumanReview />;
  else if (seg === "audit") page = <Audit initialCase={id} />;
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-ink-900/60 p-4 backdrop-blur md:flex">
        <a href="#/" className="mb-8 flex items-center gap-2.5 px-2 pt-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 ring-1 ring-accent/40"><ShieldCheck className="h-4 w-4 text-accent" /></div>
          <div><div className="text-sm font-semibold tracking-[0.18em] text-white">RECLAIM OS</div><div className="text-[10px] text-slate-500">Revenue Recovery</div></div>
        </a>
        <nav className="space-y-1">
          {NAV.map((n) => {
            const on = "/" + seg === n.to;
            return (
              <a key={n.to} href={`#${n.to}`} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${on ? "bg-accent/10 text-accent ring-1 ring-accent/25" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"}`}>
                <n.icon className="h-4 w-4" />{n.label}
              </a>
            );
          })}
        </nav>
        <div className="mt-auto space-y-2 rounded-xl border border-white/[0.06] p-3 text-[11px] leading-relaxed text-slate-500">
          <SimTag />
          <div>All customers, payments and recoveries are synthetic. No real money moves; the simulator is deterministic.</div>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <div className="flex gap-1 overflow-x-auto border-b border-white/[0.06] p-2 md:hidden">
          {NAV.map((n) => <a key={n.to} href={`#${n.to}`} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${"/" + seg === n.to ? "bg-accent/10 text-accent" : "text-slate-400"}`}>{n.label}</a>)}
        </div>
        <div className="mx-auto max-w-[1400px] p-6 lg:p-8 fade-in" key={path}>{page}</div>
      </main>
    </div>
  );
}
