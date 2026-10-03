"""Integration tests against the real API and seeded demo DB (in-memory SQLite)."""
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import RecoveryCase, AuditEvent


def scen(client):
    return {s["key"]: s for s in client.get("/api/scenarios").json()}


def metrics(client):
    return client.get("/api/dashboard").json()["metrics"]


def events(client, cid):
    return [e["event_type"] for e in client.get(f"/api/audit?case_id={cid}&order=asc&limit=500").json()["items"]]


def test_health_and_docs(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "RECLAIM OS API"


def test_seed_volumes_meet_spec(client):
    d = client.get("/api/dashboard").json()
    assert d["label"].startswith("DEMO")
    assert client.get("/api/customers?limit=1").json()["total"] >= 1000
    assert client.get("/api/recovery-cases?limit=1").json()["total"] >= 100
    m = d["metrics"]
    assert m["revenue_at_risk"] > m["recoverable_revenue"] > 0 and m["human_escalations"] >= 1 and m["blocked_actions"] >= 1


def test_six_scenarios_available(client):
    s = scen(client)
    assert len(s) == 6 and s["S3_HUMAN_ESCALATION"]["decision"] == "ESCALATE" and s["S4_ALREADY_PAID"]["decision"] == "NO_ACTION"


def test_case_detail_has_explanation_candidates_and_policy(client):
    cid = scen(client)["S2_LINK_SUCCESS"]["case_id"]
    d = client.get(f"/api/recovery-cases/{cid}").json()
    a = d["analysis"]
    assert a["selected_action"] == "PAYMENT_LINK" and a["root_cause"].startswith("Expired")
    assert len(a["candidates"]) >= 5 and a["explanation"]["stopping_condition"] and a["score_reasons"]
    retry = next(c for c in a["candidates"] if c["action"] == "RETRY_PAYMENT")
    assert retry["policy_status"] == "BLOCK"
    assert d["label"] == "DEMO / SIMULATED"


def test_analyze_endpoint_logs_decision_chain(client):
    cid = scen(client)["S1_RETRY_SUCCESS"]["case_id"]
    r = client.post(f"/api/recovery-cases/{cid}/analyze")
    assert r.status_code == 200 and r.json()["decision"] == "ACT"
    ev = events(client, cid)
    for e in ("CASE_CREATED", "RISK_CALCULATED", "ROOT_CAUSE_IDENTIFIED", "ACTION_RECOMMENDED", "POLICY_CHECKED", "ACTION_ALLOWED"):
        assert e in ev


def test_scenario1_retry_success_updates_metrics_and_audit(client):
    s = scen(client)["S1_RETRY_SUCCESS"]
    before = metrics(client)["revenue_recovered"]
    r = client.post(f"/api/recovery-cases/{s['case_id']}/execute").json()
    assert r["action"] == "RETRY_PAYMENT" and r["result"] == "SUCCESS" and r["amount_recovered"] == 18500 and r["simulated"]
    assert metrics(client)["revenue_recovered"] == before + 18500
    ev = events(client, s["case_id"])
    assert "ACTION_EXECUTED" in ev and "PAYMENT_SUCCEEDED" in ev and ev[-1] == "CASE_RESOLVED"
    assert client.get(f"/api/recovery-cases/{s['case_id']}").json()["status"] == "RECOVERED"


def test_cannot_execute_closed_case(client):
    cid = scen(client)["S1_RETRY_SUCCESS"]["case_id"]
    r = client.post(f"/api/recovery-cases/{cid}/execute")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_CLOSED"


def test_scenario2_payment_link_success(client):
    s = scen(client)["S2_LINK_SUCCESS"]
    r = client.post(f"/api/recovery-cases/{s['case_id']}/execute").json()
    assert r["action"] == "PAYMENT_LINK" and r["result"] == "SUCCESS" and r["amount_recovered"] == 85000


def test_scenario6_checkout_recovery(client):
    s = scen(client)["S6_CHECKOUT_RECOVERY"]
    r = client.post(f"/api/recovery-cases/{s['case_id']}/execute").json()
    assert r["action"] == "CHECKOUT_RECOVERY" and r["result"] == "SUCCESS"


def test_scenario3_requires_approval_then_executes(client):
    s = scen(client)["S3_HUMAN_ESCALATION"]
    cid = s["case_id"]
    blocked = client.post(f"/api/recovery-cases/{cid}/execute")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "APPROVAL_REQUIRED"
    q = client.get("/api/reviews?status=OPEN").json()["items"]
    rv = next(x for x in q if x["case_id"] == cid)
    assert rv["amount"] == 480000 and rv["high_value"] and "HUMAN_APPROVAL_THRESHOLD" in rv["policy_conflict"]
    r = client.post(f"/api/recovery-cases/{cid}/approve", json={"by": "tester", "note": "ok"}).json()
    assert r["result"] == "SUCCESS" and r["amount_recovered"] == 480000
    ev = events(client, cid)
    assert "HUMAN_ESCALATED" in ev and "HUMAN_APPROVED" in ev and "ACTION_EXECUTED" in ev
    assert client.post(f"/api/recovery-cases/{cid}/approve").status_code == 409


def test_reject_and_request_info_flow(client):
    q = client.get("/api/reviews?status=OPEN").json()["items"]
    assert len(q) >= 2
    a, b = q[0]["case_id"], q[1]["case_id"]
    assert client.post(f"/api/recovery-cases/{a}/request-info", json={"note": "need KYC"}).json()["result"] == "INFO_REQUESTED"
    r = client.post(f"/api/recovery-cases/{a}/reject", json={"by": "tester"}).json()
    assert r["result"] == "REJECTED" and r["amount_recovered"] == 0
    assert "HUMAN_REJECTED" in events(client, a)
    assert client.post(f"/api/recovery-cases/{a}/execute").status_code == 409
    assert client.post(f"/api/recovery-cases/{b}/reject").status_code == 200


def test_scenario4_no_action_already_paid(client):
    s = scen(client)["S4_ALREADY_PAID"]
    d = client.get(f"/api/recovery-cases/{s['case_id']}").json()
    assert d["decision"] == "NO_ACTION" and "already resolved" in d["analysis"]["decision_reason"].lower()
    r = client.post(f"/api/recovery-cases/{s['case_id']}/execute").json()
    assert r["result"] == "NO_ACTION" and r["amount_recovered"] == 0
    assert "NO_ACTION_SELECTED" in events(client, s["case_id"])


def test_scenario5_blocked_by_retry_limit(client):
    s = scen(client)["S5_RETRY_LIMIT"]
    d = client.get(f"/api/recovery-cases/{s['case_id']}").json()
    assert d["status"] == "BLOCKED" and d["analysis"]["blocked_top"]["action"] == "RETRY_PAYMENT"
    assert "Retry limit exceeded" in d["analysis"]["blocked_top"]["policy_reasons"][0]
    assert "ACTION_BLOCKED" in events(client, s["case_id"])


def test_two_failed_attempts_stop_the_case(client):
    cid = scen(client)["S1_GRAPH"]["case_id"] if "S1_GRAPH" in scen(client) else None
    with SessionLocal() as db:
        c = db.scalars(select(RecoveryCase).where(RecoveryCase.scenario == "S1_GRAPH", RecoveryCase.source_type == "subscription")).one()
        cid = c.id
        c.context = {**c.context, "forced_outcome": ["FAILED", "FAILED"]}
        db.commit()
    r1 = client.post(f"/api/recovery-cases/{cid}/execute").json()
    assert r1["result"] == "FAILED" and r1["status"] == "ATTEMPT_FAILED"
    r2 = client.post(f"/api/recovery-cases/{cid}/execute").json()
    assert r2["result"] == "FAILED" and r2["status"] == "STOPPED"
    ev = events(client, cid)
    assert ev.count("PAYMENT_FAILED") == 2
    assert client.post(f"/api/recovery-cases/{cid}/execute").status_code == 409


def test_customer_graph_aggregates_exposure(client):
    cu = next(c for c in client.get("/api/customers?q=Aarav Sharma&limit=5").json()["items"] if c["email"] == "aarav.sharma@example.com")
    g = client.get(f"/api/customers/{cu['id']}").json()
    assert {n["type"] for n in g["nodes"]} == {"payment", "checkout", "subscription", "invoice"}
    assert g["total_exposure"] == pytest.approx(sum(n["exposure"] for n in g["nodes"]))
    assert g["by_source"]["invoice"] == 80000


def test_audit_filters(client):
    all_ = client.get("/api/audit?limit=5").json()
    assert all_["total"] > 100 and len(all_["items"]) == 5
    ts = [e["timestamp"] for e in all_["items"]]
    assert ts == sorted(ts, reverse=True)
    pol = client.get("/api/audit?event_type=POLICY_CHECKED&policy=HUMAN_APPROVAL").json()
    assert pol["total"] >= 1 and all(e["event_type"] == "POLICY_CHECKED" for e in pol["items"])
    assert client.get("/api/audit?actor=POLICY_GATE&outcome=BLOCK&limit=3").json()["total"] >= 1


def test_experiment_run_separates_observed_from_incremental(client):
    r = client.post("/api/experiments/run", json={"split": 0.5, "seed": 11}).json()
    assert r["label"] == "SIMULATED" and r["ai"]["cases"] > 0 and r["control"]["cases"] > 0
    assert "observed_recovery" in r and "incremental_recovery" in r and r["observed_recovery"] != r["incremental_recovery"]
    assert client.get("/api/experiments").json()["items"][0]["seed"] == 11
    assert client.post("/api/experiments/run", json={"split": 1.5}).status_code == 422


def test_recovery_lab_case_and_simulation(client):
    cid = scen(client)["S2_LINK_SUCCESS"]["case_id"]
    lab = client.get(f"/api/recovery-lab/{cid}").json()
    assert all(c["estimate_label"] == "ESTIMATED" for c in lab["candidates"]) and lab["actual"][0]["result"] == "SUCCESS"
    opt = client.post("/api/recovery-lab/simulate", json={"strategy": "OPTIMIZER", "contact_frequency": 6}).json()
    blanket = client.post("/api/recovery-lab/simulate", json={"strategy": "BLANKET_OUTREACH", "contact_frequency": 6}).json()
    assert opt["label"].startswith("SIMULATION") and opt["policy_violations"] == 0 and opt["effective_contact_frequency"] == 3
    assert blanket["policy_violations"] > 0
    assert opt["allocated"] <= opt["budget"]
    dn = client.post("/api/recovery-lab/simulate", json={"strategy": "DO_NOTHING"}).json()
    assert dn["estimated_cost"] == 0 and dn["expected_recovery"] < opt["expected_recovery"]


def test_validation_and_structured_errors(client):
    assert client.get("/api/recovery-cases/99999").json()["error"]["code"] == "CASE_NOT_FOUND"
    assert client.get("/api/customers/99999").status_code == 404
    r = client.post("/api/recovery-lab/simulate", json={"strategy": "OPTIMIZER", "budget": -5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.post("/api/recovery-lab/simulate", json={"strategy": "NOPE"}).json()["error"]["code"] == "INVALID_STRATEGY"
    assert "Traceback" not in client.get("/api/recovery-cases?limit=0").text


def test_policies_endpoint_lists_spec_limits(client):
    p = {x["key"]: x["value"] for x in client.get("/api/policies").json()}
    assert p["MAX_PAYMENT_RETRIES"] == 2 and p["MAX_CUSTOMER_MESSAGES"] == 3 and p["HUMAN_APPROVAL_THRESHOLD"] == 100000


def test_reset_restores_demo_and_scenarios_repeatable(client):
    assert client.post("/api/simulator/reset").json()["status"] == "reset"
    s = scen(client)["S1_RETRY_SUCCESS"]
    assert s["status"] == "ANALYZED"
    assert client.post(f"/api/recovery-cases/{s['case_id']}/execute").json()["result"] == "SUCCESS"
