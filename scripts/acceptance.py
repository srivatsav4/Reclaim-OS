#!/usr/bin/env python3
"""End-to-end acceptance check against a RUNNING server (API level).
Usage: python scripts/acceptance.py [http://127.0.0.1:8000]
Covers the demo story: dashboard -> case -> analyze -> policy -> execute -> audit -> human review -> experiment -> lab -> reset -> repeat."""
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=60)
n = 0


def step(msg, ok, detail=""):
    global n
    n += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {n:02d} {msg} {detail}")
    if not ok:
        sys.exit(1)


def flow(label):
    c.post("/api/simulator/reset").raise_for_status()
    d = c.get("/api/dashboard").json()
    step(f"{label}: dashboard metrics present", d["metrics"]["revenue_at_risk"] > 0 and d["label"].startswith("DEMO"),
         f"at_risk={d['metrics']['revenue_at_risk']:.0f}")
    before = d["metrics"]["revenue_recovered"]
    sc = {s["key"]: s for s in c.get("/api/scenarios").json()}
    step(f"{label}: 6 scenarios available", len(sc) == 6)
    cid = sc["S2_LINK_SUCCESS"]["case_id"]
    case = c.post(f"/api/recovery-cases/{cid}/analyze").json()
    a = case["analysis"]
    step(f"{label}: root cause diagnosed", "Expired" in a["root_cause"], a["root_cause"])
    step(f"{label}: candidate actions + EV math", len(a["candidates"]) >= 5 and all(
        abs(x["expected_value"] - (x["expected_recovery"] - x["cost"] - x["friction_penalty"])) < 0.05 for x in a["candidates"]))
    step(f"{label}: policy gate blocked retry, allowed link", {x["action"]: x["policy_status"] for x in a["candidates"]}["RETRY_PAYMENT"] == "BLOCK" and a["selected_action"] == "PAYMENT_LINK")
    r = c.post(f"/api/recovery-cases/{cid}/execute").json()
    step(f"{label}: executed in simulator, ₹85,000 recovered", r["result"] == "SUCCESS" and r["amount_recovered"] == 85000)
    after = c.get("/api/dashboard").json()["metrics"]["revenue_recovered"]
    step(f"{label}: dashboard updated", abs(after - before - 85000) < 1)
    ev = [e["event_type"] for e in c.get(f"/api/audit?case_id={cid}&order=asc").json()["items"]]
    step(f"{label}: audit trail records decision", all(e in ev for e in ("RISK_CALCULATED", "POLICY_CHECKED", "ACTION_ALLOWED", "ACTION_EXECUTED", "PAYMENT_SUCCEEDED")))
    h = sc["S3_HUMAN_ESCALATION"]["case_id"]
    step(f"{label}: escalated case cannot self-execute", c.post(f"/api/recovery-cases/{h}/execute").status_code == 409)
    queue = c.get("/api/reviews?status=OPEN").json()["items"]
    step(f"{label}: human review queue populated", any(q["case_id"] == h for q in queue))
    ap = c.post(f"/api/recovery-cases/{h}/approve", json={"by": "acceptance"}).json()
    other = next(q for q in queue if q["case_id"] != h)
    rj = c.post(f"/api/recovery-cases/{other['case_id']}/reject", json={"by": "acceptance"}).json()
    step(f"{label}: approve + reject work", ap["result"] == "SUCCESS" and rj["result"] == "REJECTED")
    step(f"{label}: review decisions audited", "HUMAN_APPROVED" in [e["event_type"] for e in c.get(f"/api/audit?case_id={h}").json()["items"]]
         and "HUMAN_REJECTED" in [e["event_type"] for e in c.get(f"/api/audit?case_id={other['case_id']}").json()["items"]])
    na = c.post(f"/api/recovery-cases/{sc['S4_ALREADY_PAID']['case_id']}/execute").json()
    bl = c.get(f"/api/recovery-cases/{sc['S5_RETRY_LIMIT']['case_id']}").json()
    step(f"{label}: NO ACTION and BLOCKED behave safely", na["result"] == "NO_ACTION" and bl["status"] == "BLOCKED")
    ex = c.post("/api/experiments/run", json={"split": 0.7, "seed": 42}).json()
    step(f"{label}: AI vs control separates observed and incremental", ex["ai"]["cases"] > 0 and ex["control"]["cases"] > 0 and "incremental_recovery" in ex and ex["label"] == "SIMULATED",
         f"incremental={ex['incremental_recovery']:.0f}")
    lab = c.get(f"/api/recovery-lab/{cid}").json()
    sim = c.post("/api/recovery-lab/simulate", json={"strategy": "OPTIMIZER", "budget": 10000}).json()
    step(f"{label}: recovery lab estimates labelled", all(x["estimate_label"] == "ESTIMATED" for x in lab["candidates"]) and sim["label"].startswith("SIMULATION"))


def main():
    step("health", c.get("/api/health").json()["status"] == "ok")
    step("swagger /docs", c.get("/docs").status_code == 200)
    flow("run 1")
    flow("run 2 (after reset)")
    print(f"\nACCEPTANCE: {n} checks passed")


main()
