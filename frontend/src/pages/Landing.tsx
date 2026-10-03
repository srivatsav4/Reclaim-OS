import { ArrowRight, Ban, BarChart3, ShieldCheck, Target } from "lucide-react";
import { SimTag } from "../components/ui";

const PILLARS = [
  { icon: Target, t: "Decides what to chase", d: "Customer-level revenue exposure, explainable recoverability scores and expected-value ranking under a daily budget." },
  { icon: ShieldCheck, t: "Acts inside hard limits", d: "A deterministic policy gate allows, blocks or escalates every action. AI recommends; policy decides." },
  { icon: Ban, t: "Knows when not to act", d: "NO ACTION is a first-class decision: already paid, retry limit hit, contact not permitted, value too low." },
  { icon: BarChart3, t: "Measures what it caused", d: "Observed recovery is kept separate from estimated incremental recovery against a control group." },
];

export default function Landing() {
  return (
    <div className="relative min-h-full overflow-hidden">
      <div className="grid-bg absolute inset-0 opacity-60" />
      <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
        <div className="mb-8 flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl bg-accent/15 ring-1 ring-accent/40"><ShieldCheck className="h-5 w-5 text-accent" /></div><SimTag /></div>
        <h1 className="text-6xl font-semibold tracking-[0.12em] text-white sm:text-7xl">RECLAIM <span className="text-accent">OS</span></h1>
        <p className="mt-6 text-3xl font-medium leading-tight text-slate-200 sm:text-4xl">Don't chase every failed payment.<br /><span className="text-accent">Recover the right revenue.</span></p>
        <p className="mt-6 max-w-2xl text-base leading-relaxed text-slate-400">An AI revenue recovery operating system that detects revenue leakage, chooses policy-bounded interventions, and measures incremental recovery.</p>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <a href="#/command" className="btn btn-primary !px-6 !py-3 text-base tracking-wide">OPEN COMMAND CENTER <ArrowRight className="h-4 w-4" /></a>
          <a href="#/room" className="btn btn-ghost !px-5 !py-3">Jump to AI Decision Room</a>
        </div>
        <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((p) => (
            <div key={p.t} className="card p-5"><p.icon className="mb-3 h-5 w-5 text-accent" /><div className="text-sm font-semibold text-white">{p.t}</div><p className="mt-2 text-xs leading-relaxed text-slate-500">{p.d}</p></div>
          ))}
        </div>
        <p className="mt-10 text-xs text-slate-600">Demo build: synthetic data and a local deterministic simulator. No payment gateway, LLM API or external service is used.</p>
      </div>
    </div>
  );
}
