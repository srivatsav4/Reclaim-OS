"""Case workflow: analyze -> policy gate -> execute -> outcome -> audit. Plus dashboard, graph, lab, experiments."""
from collections import defaultdict
from datetime import timedelta
import math

from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from . import engine as E
from . import simulator as S
from .db import AI_MODE, utcnow
from .models import (AgentDecision, AuditEvent, Checkout, Customer, Experiment, HumanReview, Invoice, Payment,
                     RecoveryAction, RecoveryCase, RecoveryOutcome, RecoveryPolicy, Subscription)
from .policy import (CONTACT_ACTIONS, HUMAN_REVIEW, NO_ACTION, RETRY_PAYMENT, ESCALATE, ALLOW, BLOCK, Policy, evaluate)

TERMINAL = {"RECOVERED", "STOPPED", "CONTROL_HOLD", "CONTROL_RECOVERED", "CLOSED_RESOLVED", "CLOSED_NO_ACTION", "REJECTED"}
ACTIVE = {"ANALYZED", "ESCALATED", "ATTEMPT_FAILED"}
SOURCE_MODELS = {"payment": Payment, "checkout": Checkout, "subscription": Subscription, "invoice": Invoice}


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status


def load_policy(db: Session) -> Policy:
    p = Policy()
    for row in db.scalars(select(RecoveryPolicy)):
        if hasattr(p, row.key):
            setattr(p, row.key, type(getattr(p, row.key))(row.value))
    return p


def audit(db, event_type, actor, reason, *, case=None, entity_type="case", entity_id=None, policy=None,
          outcome=None, meta=None, at=None):
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id if entity_id is not None else (case.id if case else 0),
                      case_id=case.id if case else None, customer_id=case.customer_id if case else None,
                      event_type=event_type, actor=actor, reason=reason, policy=policy, outcome=outcome,
                      meta=meta or {}, timestamp=at or utcnow()))


def get_case(db, case_id: int) -> RecoveryCase:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise AppError("CASE_NOT_FOUND", f"Recovery case {case_id} not found", 404)
    return case


def build_ctx(db, case: RecoveryCase) -> dict:
    cu = db.get(Customer, case.customer_id)
    ctx = dict(case.context or {})
    ctx.update(source_type=case.source_type, amount=case.revenue_at_risk, ltv=cu.lifetime_value, segment=cu.segment,
               contact_allowed=cu.contact_allowed, successful_payments=cu.successful_payments,
               previous_recoveries=cu.previous_recoveries, engagement=cu.engagement)
    ctx["failure_class"] = E.failure_class(ctx)
    return ctx


# ------------------------------------------------------------------ analyze
def analyze_case(db: Session, case: RecoveryCase, *, actor="RECLAIM_AGENT", at=None, first=False, quiet=False) -> dict:
    policy = load_policy(db)
    ctx = build_ctx(db, case)
    score, reasons = E.score_recoverability(ctx)
    code, label, evidence = E.diagnose(ctx)
    cands = E.build_candidates(ctx, score, policy)
    choice = E.choose_action(cands, ctx, policy)
    sel = choice["selected"]
    expl = E.explain(ctx, score, label, evidence, choice, policy)
    analysis = {"score": score, "score_reasons": reasons, "root_cause_code": code, "root_cause": label,
                "evidence": evidence, "candidates": cands, "selected_action": sel["action"], "decision": choice["decision"],
                "decision_reason": choice["reason"], "blocked_top": choice["blocked_top"], "explanation": expl,
                "analyzed_at": (at or utcnow()).isoformat()}
    case.analysis = analysis
    case.recoverability_score, case.root_cause = score, label
    case.recommended_action, case.decision = sel["action"], choice["decision"]
    case.expected_recovery = sel["expected_recovery"] if choice["decision"] != "NO_ACTION" else 0.0
    case.priority = E.priority_for(case.revenue_at_risk, ctx.get("hours_since_failure", 0))
    if case.status in ("OPEN", "ANALYZED", "ESCALATED", "ATTEMPT_FAILED", "NO_ACTION", "BLOCKED"):
        case.status = choice["status_hint"]
    case.updated_at = at or utcnow()
    if first:
        case.experiment_eligible = choice["decision"] == "ACT" and not case.scenario
        noop = choice["noop"]
        case.baseline = {"action": sel["action"], "probability": sel["probability"], "organic_p": noop["probability"]}

    db.execute(delete(RecoveryAction).where(RecoveryAction.recovery_case_id == case.id,
                                            RecoveryAction.execution_status.in_(["PLANNED", "NOT_SELECTED"])))
    for c in cands:
        db.add(RecoveryAction(recovery_case_id=case.id, action_type=c["action"], estimated_cost=c["cost"],
                              expected_probability=c["probability"], expected_recovery=c["expected_recovery"],
                              expected_value=c["expected_value"], friction=c["friction"], policy_status=c["policy_status"],
                              policy_reasons=c["policy_reasons"], selected=c["action"] == sel["action"],
                              execution_status="PLANNED" if c["action"] == sel["action"] else "NOT_SELECTED"))
    if quiet:  # execution-time policy re-check: refresh rows only, no new audit/review side effects
        db.flush()
        return analysis
    db.add(AgentDecision(recovery_case_id=case.id, decision=choice["decision"], selected_action=sel["action"],
                         reasoning=expl, mode=AI_MODE, created_at=at or utcnow()))

    t = at or utcnow()
    audit(db, "RISK_CALCULATED", actor, f"Recoverability {score}/100", case=case, at=t, meta={"reasons": reasons})
    audit(db, "ROOT_CAUSE_IDENTIFIED", actor, label, case=case, at=t + timedelta(milliseconds=1), meta={"code": code})
    audit(db, "ACTION_RECOMMENDED", actor, f"{sel['action']} recommended (EV {E.inr(sel['expected_value'])})", case=case,
          at=t + timedelta(milliseconds=2), meta={"candidates": [(c["action"], c["expected_value"]) for c in cands]})
    audit(db, "POLICY_CHECKED", "POLICY_GATE", "; ".join(sel["policy_reasons"]), case=case, at=t + timedelta(milliseconds=3),
          policy=",".join(sel["policy_rules"]) or "WITHIN_LIMITS", outcome=sel["policy_status"])
    if choice["blocked_top"]:
        bt = choice["blocked_top"]
        audit(db, "ACTION_BLOCKED", "POLICY_GATE", f"{bt['action']} blocked: {bt['policy_reasons'][0]}", case=case,
              at=t + timedelta(milliseconds=4), policy=",".join(bt["policy_rules"]), outcome="BLOCK")
    if choice["decision"] == "ACT":
        audit(db, "ACTION_ALLOWED", "POLICY_GATE", f"{sel['action']} allowed", case=case, at=t + timedelta(milliseconds=5),
              policy="WITHIN_LIMITS", outcome="ALLOW")
    elif choice["decision"] == "ESCALATE":
        audit(db, "HUMAN_ESCALATED", "POLICY_GATE", choice["reason"], case=case, at=t + timedelta(milliseconds=5),
              policy=",".join(sel["policy_rules"]), outcome="ESCALATE")
        pending = db.scalar(select(HumanReview).where(HumanReview.recovery_case_id == case.id,
                                                      HumanReview.status.in_(["PENDING", "INFO_REQUESTED"])))
        if not pending:
            db.add(HumanReview(recovery_case_id=case.id, reason=choice["reason"],
                               policy_conflict=", ".join(sel["policy_rules"]), recommended_action=sel["action"],
                               recommended_step=f"Approve to execute {sel['action']} (expected {E.inr(sel['expected_recovery'])})"
                               if sel["action"] != HUMAN_REVIEW else "Assign to an account manager for manual outreach",
                               created_at=t))
    else:
        audit(db, "NO_ACTION_SELECTED", actor, choice["reason"], case=case, at=t + timedelta(milliseconds=5),
              outcome=choice["status_hint"])
    db.flush()
    return analysis


# ------------------------------------------------------------------ execute
def _apply_source_success(db, case, at):
    src = db.get(SOURCE_MODELS[case.source_type], case.source_id)
    if not src:
        return
    if case.source_type == "payment":
        src.status, src.resolved_at = "RECOVERED", at
    elif case.source_type == "checkout":
        src.status = "RECOVERED"
    elif case.source_type == "subscription":
        src.status, src.failure_count = "ACTIVE", 0
    else:
        src.status = "PAID"


def execute_case(db: Session, case_id: int, *, actor="RECLAIM_AGENT", approved_by=None, at=None) -> dict:
    case = get_case(db, case_id)
    if case.status in TERMINAL:
        raise AppError("CASE_CLOSED", f"Case is already {case.status}; nothing to execute", 409)
    if not case.analysis:
        analyze_case(db, case)
    # Always re-run the gate on the latest state before acting.
    analyze_case(db, case, actor=actor, at=at, quiet=True)
    a = case.analysis
    t = at or utcnow()
    if case.decision == "ESCALATE" and not approved_by:
        raise AppError("APPROVAL_REQUIRED", "Policy requires human approval before this action can execute", 409)
    if case.decision == "NO_ACTION":
        case.status = "BLOCKED" if case.status == "BLOCKED" else ("CLOSED_RESOLVED" if case.context.get("already_resolved") else "CLOSED_NO_ACTION")
        audit(db, "CASE_RESOLVED", actor, f"Closed with no action: {a['decision_reason']}", case=case, at=t, outcome="NO_ACTION")
        return {"case_id": case.id, "result": "NO_ACTION", "amount_recovered": 0.0, "message": a["decision_reason"], "status": case.status}

    ctx = build_ctx(db, case)
    sel = next(c for c in a["candidates"] if c["action"] == a["selected_action"])
    row = db.scalar(select(RecoveryAction).where(RecoveryAction.recovery_case_id == case.id,
                                                 RecoveryAction.action_type == sel["action"],
                                                 RecoveryAction.execution_status == "PLANNED"))
    allowed = sel["policy_status"] in (ALLOW, ESCALATE)
    sim = S.simulate_action(case.id, sel["action"], sel["probability"], already_resolved=ctx.get("already_resolved", False),
                            allowed=allowed, forced=case.context.get("forced_outcome"),
                            attempt=ctx.get("failed_attempts", 0))
    result = sim["result"]
    audit(db, "ACTION_EXECUTED", actor if not approved_by else approved_by,
          f"{sel['action']} executed in simulator ({sim['note']})", case=case, at=t, outcome=result,
          meta={"action": sel["action"], "simulated": True})
    recovered = case.revenue_at_risk if result == S.SUCCESS else 0.0
    new_ctx = dict(case.context)
    if sel["action"] in CONTACT_ACTIONS or sel["action"] == HUMAN_REVIEW:
        new_ctx["messages_sent"] = new_ctx.get("messages_sent", 0) + 1
        new_ctx["last_message_hours_ago"] = 0
    if sel["action"] == RETRY_PAYMENT:
        new_ctx["retries_done"] = new_ctx.get("retries_done", 0) + 1
    organic_p = case.baseline.get("organic_p", 0.05) if case.baseline else 0.05
    if result == S.SUCCESS:
        case.status, case.actual_recovery = "RECOVERED", recovered
        _apply_source_success(db, case, t)
        db.get(Customer, case.customer_id).previous_recoveries += 1
        audit(db, "PAYMENT_SUCCEEDED", "SIMULATOR", f"{E.inr(recovered)} recovered (simulated)", case=case,
              at=t + timedelta(milliseconds=1), outcome=result)
        audit(db, "CASE_RESOLVED", "SIMULATOR", "Case resolved: revenue recovered", case=case,
              at=t + timedelta(milliseconds=2), outcome=result)
    elif result == S.ALREADY_RESOLVED:
        case.status = "CLOSED_RESOLVED"
        audit(db, "CASE_RESOLVED", "SIMULATOR", "Customer had already resolved this", case=case, at=t, outcome=result)
    elif result == S.BLOCKED:
        case.status = "BLOCKED"
        audit(db, "ACTION_BLOCKED", "POLICY_GATE", "Blocked at execution time", case=case, at=t, outcome=result)
    else:
        new_ctx["failed_attempts"] = new_ctx.get("failed_attempts", 0) + 1
        case.status = "ATTEMPT_FAILED"
        audit(db, "PAYMENT_FAILED", "SIMULATOR", f"Recovery attempt {new_ctx['failed_attempts']} failed ({result})",
              case=case, at=t + timedelta(milliseconds=1), outcome=result)
        if new_ctx["failed_attempts"] >= load_policy(db).MAX_FAILED_RECOVERY_ATTEMPTS:
            case.status = "STOPPED"
            audit(db, "CASE_RESOLVED", "POLICY_GATE", "Stopping condition reached; automation halted", case=case,
                  at=t + timedelta(milliseconds=2), policy="MAX_FAILED_RECOVERY_ATTEMPTS", outcome="STOPPED")
    case.context = new_ctx
    case.executed_at = t
    case.updated_at = t
    if row:
        row.execution_status, row.executed_at = result, t
        out = RecoveryOutcome(recovery_action_id=row.id, recovery_case_id=case.id, result=result, amount_recovered=recovered,
                              incremental_recovery=round(max(0.0, recovered - organic_p * case.revenue_at_risk), 2)
                              if result == S.SUCCESS else 0.0, timestamp=t)
        db.add(out)
    db.flush()
    return {"case_id": case.id, "action": sel["action"], "result": result, "amount_recovered": recovered,
            "message": sim["note"], "status": case.status, "simulated": True}


# ------------------------------------------------------------------ human review
def _pending_review(db, case_id):
    r = db.scalar(select(HumanReview).where(HumanReview.recovery_case_id == case_id,
                                            HumanReview.status.in_(["PENDING", "INFO_REQUESTED"])))
    if not r:
        raise AppError("NO_PENDING_REVIEW", "This case has no pending human review", 409)
    return r


def approve_case(db, case_id, by="reviewer", note=None, at=None):
    case = get_case(db, case_id)
    r = _pending_review(db, case_id)
    r.status, r.decided_at, r.decided_by, r.note = "APPROVED", at or utcnow(), by, note
    audit(db, "HUMAN_APPROVED", by, note or "Approved by human reviewer", case=case, at=at, outcome="APPROVED")
    return execute_case(db, case_id, actor=by, approved_by=by, at=at)


def reject_case(db, case_id, by="reviewer", note=None, at=None):
    case = get_case(db, case_id)
    r = _pending_review(db, case_id)
    r.status, r.decided_at, r.decided_by, r.note = "REJECTED", at or utcnow(), by, note
    case.status, case.updated_at = "REJECTED", at or utcnow()
    audit(db, "HUMAN_REJECTED", by, note or "Rejected by human reviewer", case=case, at=at, outcome="REJECTED")
    audit(db, "CASE_RESOLVED", by, "Case closed without recovery action", case=case, at=at, outcome="REJECTED")
    return {"case_id": case.id, "result": "REJECTED", "status": case.status, "amount_recovered": 0.0}


def request_info(db, case_id, by="reviewer", note=None):
    case = get_case(db, case_id)
    r = _pending_review(db, case_id)
    r.status, r.note = "INFO_REQUESTED", note or "More information requested"
    audit(db, "HUMAN_INFO_REQUESTED", by, r.note, case=case, outcome="INFO_REQUESTED")
    return {"case_id": case.id, "result": "INFO_REQUESTED", "status": case.status}


# ------------------------------------------------------------------ serializers
def case_dict(c: RecoveryCase, cu: Customer | None = None, full=False) -> dict:
    d = {"id": c.id, "customer_id": c.customer_id, "customer_name": cu.name if cu else None,
         "segment": cu.segment if cu else None, "source_type": c.source_type, "source_id": c.source_id,
         "revenue_at_risk": c.revenue_at_risk, "recoverability_score": c.recoverability_score, "priority": c.priority,
         "status": c.status, "root_cause": c.root_cause, "recommended_action": c.recommended_action,
         "expected_recovery": c.expected_recovery, "actual_recovery": c.actual_recovery, "decision": c.decision,
         "group": c.group, "scenario": c.scenario, "created_at": c.created_at.isoformat(),
         "executed_at": c.executed_at.isoformat() if c.executed_at else None, "label": "DEMO / SIMULATED"}
    if full:
        d["analysis"], d["context"] = c.analysis, c.context
    return d


def review_dict(db, r: HumanReview) -> dict:
    c = db.get(RecoveryCase, r.recovery_case_id)
    cu = db.get(Customer, c.customer_id)
    return {"id": r.id, "case_id": c.id, "status": r.status, "customer": cu.name, "customer_id": cu.id,
            "amount": c.revenue_at_risk, "risk": c.priority, "reason": r.reason, "policy_conflict": r.policy_conflict,
            "recommended_action": r.recommended_action, "recommended_step": r.recommended_step,
            "root_cause": c.root_cause, "score": c.recoverability_score, "expected_recovery": c.expected_recovery,
            "high_value": c.revenue_at_risk >= load_policy(db).HIGH_VALUE_THRESHOLD,
            "created_at": r.created_at.isoformat(), "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "decided_by": r.decided_by, "note": r.note, "case_status": c.status}


def action_dict(a: RecoveryAction) -> dict:
    return {"id": a.id, "case_id": a.recovery_case_id, "action_type": a.action_type, "estimated_cost": a.estimated_cost,
            "expected_probability": a.expected_probability, "expected_recovery": a.expected_recovery,
            "expected_value": a.expected_value, "friction": a.friction, "policy_status": a.policy_status,
            "policy_reasons": a.policy_reasons, "selected": a.selected, "execution_status": a.execution_status,
            "executed_at": a.executed_at.isoformat() if a.executed_at else None}


def audit_dict(e: AuditEvent) -> dict:
    return {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id, "case_id": e.case_id,
            "customer_id": e.customer_id, "event_type": e.event_type, "actor": e.actor, "reason": e.reason,
            "policy": e.policy, "outcome": e.outcome, "metadata": e.meta, "timestamp": e.timestamp.isoformat()}


# ------------------------------------------------------------------ customer graph
def customer_graph(db, customer_id: int) -> dict:
    cu = db.get(Customer, customer_id)
    if not cu:
        raise AppError("CUSTOMER_NOT_FOUND", f"Customer {customer_id} not found", 404)
    cases = list(db.scalars(select(RecoveryCase).where(RecoveryCase.customer_id == customer_id).order_by(RecoveryCase.id)))
    nodes, by_source, total = [], defaultdict(float), 0.0
    for c in cases:
        resolved = c.status in ("RECOVERED", "CLOSED_RESOLVED", "CONTROL_RECOVERED") or c.context.get("already_resolved")
        exposure = 0.0 if resolved else c.revenue_at_risk
        total += exposure
        by_source[c.source_type] += exposure
        nodes.append({"case_id": c.id, "type": c.source_type, "source_id": c.source_id, "amount": c.revenue_at_risk,
                      "exposure": exposure, "case_status": c.status, "decision": c.decision,
                      "root_cause": c.root_cause, "scenario": c.scenario})
    return {"customer": {"id": cu.id, "name": cu.name, "email": cu.email, "segment": cu.segment,
                         "lifetime_value": cu.lifetime_value, "contact_allowed": cu.contact_allowed,
                         "preferred_channel": cu.preferred_channel, "risk_level": cu.risk_level,
                         "successful_payments": cu.successful_payments, "previous_recoveries": cu.previous_recoveries,
                         "engagement": cu.engagement},
            "total_exposure": total, "by_source": dict(by_source), "nodes": nodes}


# ------------------------------------------------------------------ dashboard
def budget_plan(db, policy: Policy | None = None) -> dict:
    policy = policy or load_policy(db)
    cases = list(db.scalars(select(RecoveryCase).where(RecoveryCase.status == "ANALYZED", RecoveryCase.decision == "ACT")))
    opps = []
    for c in cases:
        sel = next(x for x in c.analysis["candidates"] if x["action"] == c.analysis["selected_action"])
        opps.append({"id": c.id, "cost": sel["cost"], "expected_value": sel["expected_value"],
                     "expected_recovery": sel["expected_recovery"], "revenue_at_risk": c.revenue_at_risk})
    plan = E.allocate_budget(opps, policy.DAILY_RECOVERY_BUDGET)
    plan["pending_opportunities"] = len(opps)
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    plan["spent_today"] = float(db.scalar(select(func.coalesce(func.sum(RecoveryAction.estimated_cost), 0.0)).where(
        RecoveryAction.executed_at >= start, RecoveryAction.execution_status.in_(["SUCCESS", "FAILED", "CUSTOMER_DECLINED"]))))
    return plan


def dashboard(db: Session) -> dict:
    policy = load_policy(db)
    cases = list(db.scalars(select(RecoveryCase)))
    cust = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_({c.customer_id for c in cases})))}
    open_risk = [c for c in cases if not c.context.get("already_resolved")]
    at_risk = sum(c.revenue_at_risk for c in open_risk)
    recoverable = sum(c.expected_recovery for c in open_risk if c.decision in ("ACT", "ESCALATE"))
    recovered = sum(c.actual_recovery for c in cases)
    eligible = [c for c in open_risk if c.decision in ("ACT", "ESCALATE")]
    targeted = [c for c in cases if c.executed_at and c.context.get("messages_sent", 0) + c.context.get("retries_done", 0) >= 0
                and c.status in ("RECOVERED", "ATTEMPT_FAILED", "STOPPED")]
    exp = db.scalar(select(Experiment).order_by(Experiment.id.desc()))
    incremental = exp.results.get("incremental_recovery", 0.0) if exp else 0.0
    blocked = sum(1 for c in cases if c.analysis and c.analysis.get("blocked_top"))
    pending_reviews = db.scalar(select(func.count()).select_from(HumanReview).where(HumanReview.status.in_(["PENDING", "INFO_REQUESTED"])))
    risk_src, seg = defaultdict(float), defaultdict(lambda: {"at_risk": 0.0, "recovered": 0.0, "cases": 0})
    causes = defaultdict(lambda: {"cases": 0, "amount": 0.0})
    for c in open_risk:
        risk_src[c.source_type] += c.revenue_at_risk
        cu = cust.get(c.customer_id)
        seg[cu.segment]["at_risk"] += c.revenue_at_risk
        seg[cu.segment]["cases"] += 1
        seg[cu.segment]["recovered"] += c.actual_recovery
        causes[c.root_cause]["cases"] += 1
        causes[c.root_cause]["amount"] += c.revenue_at_risk
    by_action = defaultdict(lambda: {"recovered": 0.0, "count": 0, "attempts": 0})
    trend = defaultdict(float)
    for o, a in db.execute(select(RecoveryOutcome, RecoveryAction).join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id)):
        by_action[a.action_type]["attempts"] += 1
        if o.result == "SUCCESS":
            by_action[a.action_type]["recovered"] += o.amount_recovered
            by_action[a.action_type]["count"] += 1
            trend[o.timestamp.date().isoformat()] += o.amount_recovered
    today = utcnow().date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    return {
        "label": "DEMO / SIMULATED DATA",
        "metrics": {"revenue_at_risk": at_risk, "recoverable_revenue": recoverable, "revenue_recovered": recovered,
                    "incremental_recovery": incremental, "recovery_rate": (recovered / at_risk) if at_risk else 0.0,
                    "active_cases": sum(1 for c in cases if c.status in ACTIVE), "human_escalations": pending_reviews,
                    "blocked_actions": blocked, "total_cases": len(cases)},
        "funnel": [{"stage": "AT_RISK", "cases": len(open_risk), "amount": at_risk},
                   {"stage": "ELIGIBLE", "cases": len(eligible), "amount": sum(c.revenue_at_risk for c in eligible)},
                   {"stage": "TARGETED", "cases": len(targeted), "amount": sum(c.revenue_at_risk for c in targeted)},
                   {"stage": "RECOVERED", "cases": sum(1 for c in cases if c.status == "RECOVERED"), "amount": recovered}],
        "risk_by_source": [{"source": k, "amount": v} for k, v in sorted(risk_src.items(), key=lambda x: -x[1])],
        "recovery_by_action": [{"action": k, **v} for k, v in sorted(by_action.items(), key=lambda x: -x[1]["recovered"])],
        "recovery_trend": [{"date": d, "recovered": trend.get(d, 0.0)} for d in days],
        "top_failure_reasons": [{"reason": k, **v} for k, v in sorted(causes.items(), key=lambda x: -x[1]["amount"])[:8]],
        "segments": [{"segment": k, **v} for k, v in seg.items()],
        "budget": budget_plan(db, policy),
        "experiment": experiment_dict(exp) if exp else None,
    }


# ------------------------------------------------------------------ experiments
def _rate(rows):
    n = len(rows)
    risk = sum(r["amount"] for r in rows)
    rec = sum(r["recovered"] for r in rows)
    succ = sum(1 for r in rows if r["recovered"] > 0)
    return {"cases": n, "at_risk": risk, "recovered": rec, "successes": succ,
            "rate_value": rec / risk if risk else 0.0, "rate_cases": succ / n if n else 0.0}


def compute_experiment(rows_ai: list, rows_ctl: list) -> dict:
    ai, ctl = _rate(rows_ai), _rate(rows_ctl)
    lift = ai["rate_cases"] - ctl["rate_cases"]
    se = math.sqrt((ai["rate_cases"] * (1 - ai["rate_cases"]) / ai["cases"] if ai["cases"] else 0) +
                   (ctl["rate_cases"] * (1 - ctl["rate_cases"]) / ctl["cases"] if ctl["cases"] else 0))
    incremental = (ai["rate_value"] - ctl["rate_value"]) * ai["at_risk"]
    return {"ai": ai, "control": ctl, "observed_recovery": ai["recovered"], "incremental_recovery": incremental,
            "lift_pp": lift * 100, "ci95_pp": [(lift - 1.96 * se) * 100, (lift + 1.96 * se) * 100],
            "note": "SIMULATED experiment on deterministic demo data. Incremental recovery is an estimate "
                    "(AI-group rate minus control-group rate, applied to AI-group revenue at risk); it is not proof of causality."}


def run_experiment(db: Session, split=0.7, seed=42, name=None) -> Experiment:
    """Shadow experiment: assign every eligible case to AI or CONTROL by seeded hash and simulate both arms."""
    cases = list(db.scalars(select(RecoveryCase).where(RecoveryCase.experiment_eligible == True)))  # noqa: E712
    ai_rows, ctl_rows = [], []
    for c in cases:
        b = c.baseline
        if S.assign_group(c.id, seed, split) == "AI":
            sim = S.simulate_action(c.id, b["action"], b["probability"], attempt=0)
            ai_rows.append({"amount": c.revenue_at_risk, "recovered": c.revenue_at_risk if sim["result"] == S.SUCCESS else 0.0})
        else:
            ctl_rows.append({"amount": c.revenue_at_risk,
                             "recovered": c.revenue_at_risk if S.simulate_control(c.id, b["organic_p"]) else 0.0})
    res = compute_experiment(ai_rows, ctl_rows)
    exp = Experiment(name=name or f"AI vs Control (seed {seed}, {int(split * 100)}% AI)", split=split, seed=seed,
                     results=res, label="SIMULATED", created_at=utcnow())
    db.add(exp)
    db.flush()
    audit(db, "EXPERIMENT_RUN", "EXPERIMENT_ENGINE", f"{exp.name}: estimated incremental {E.inr(res['incremental_recovery'])}",
          entity_type="experiment", entity_id=exp.id, outcome="SIMULATED")
    return exp


def experiment_dict(e: Experiment) -> dict:
    return {"id": e.id, "name": e.name, "split": e.split, "seed": e.seed, "label": e.label,
            "created_at": e.created_at.isoformat(), **e.results}


# ------------------------------------------------------------------ recovery lab
def lab_case(db, case_id: int) -> dict:
    c = get_case(db, case_id)
    if not c.analysis:
        analyze_case(db, c)
    a = c.analysis
    cands = sorted(a["candidates"], key=lambda x: -x["expected_value"])
    outs = list(db.scalars(select(RecoveryOutcome).where(RecoveryOutcome.recovery_case_id == c.id)))
    return {"case_id": c.id, "label": "ESTIMATED (simulation, not actual recovery)", "revenue_at_risk": c.revenue_at_risk,
            "selected_action": a["selected_action"], "decision": a["decision"],
            "candidates": [{**x, "estimate_label": "ESTIMATED", "selected": x["action"] == a["selected_action"]} for x in cands],
            "actual": [{"result": o.result, "amount_recovered": o.amount_recovered, "timestamp": o.timestamp.isoformat()} for o in outs]}


STRATEGIES = {"OPTIMIZER", "RETRY_ONLY", "BLANKET_OUTREACH", "DO_NOTHING"}


def lab_simulate(db, *, budget, segment, strategy, retry_delay_hours, contact_frequency) -> dict:
    if strategy not in STRATEGIES:
        raise AppError("INVALID_STRATEGY", f"strategy must be one of {sorted(STRATEGIES)}", 422)
    policy = load_policy(db)
    pool = list(db.scalars(select(RecoveryCase).where(RecoveryCase.status.in_(["ANALYZED", "ESCALATED", "ATTEMPT_FAILED", "NO_ACTION", "BLOCKED", "OPEN"]))))
    cust = {c.id: c for c in db.scalars(select(Customer))}
    f = min(contact_frequency, policy.MAX_CUSTOMER_MESSAGES) if strategy == "OPTIMIZER" else contact_frequency
    opps, violations = [], 0
    organic = 0.0
    for c in pool:
        if segment != "ALL" and cust[c.customer_id].segment != segment:
            continue
        if c.context.get("already_resolved"):
            continue
        cands = {x["action"]: x for x in c.analysis["candidates"]}
        organic += cands[NO_ACTION]["expected_recovery"]
        if strategy == "DO_NOTHING":
            continue
        if strategy == "OPTIMIZER":
            if c.decision == "NO_ACTION":
                continue
            pick = dict(next(x for x in c.analysis["candidates"] if x["action"] == c.analysis["selected_action"]))
        elif strategy == "RETRY_ONLY":
            pick = cands.get(RETRY_PAYMENT)
            if not pick:
                continue
            pick = dict(pick)
        else:
            pick = cands.get("CUSTOMER_EMAIL") or cands.get("CHECKOUT_RECOVERY")
            if not pick:
                continue
            pick = dict(pick)
        if pick["action"] == RETRY_PAYMENT:
            pick["probability"] = min(0.95, pick["probability"] * E.retry_delay_factor(retry_delay_hours) / E.retry_delay_factor(48))
            pick["expected_recovery"] = c.revenue_at_risk * pick["probability"]
        if pick["action"] in CONTACT_ACTIONS and f > 1:
            pick["cost"] = pick["cost"] * f
            pick["expected_recovery"] *= 1 + 0.05 * (f - 1)
            pick["friction_penalty"] *= f
        pick["expected_value"] = pick["expected_recovery"] - pick["cost"] - pick["friction_penalty"]
        viol = pick["policy_status"] == BLOCK or (pick["action"] in CONTACT_ACTIONS and f > policy.MAX_CUSTOMER_MESSAGES)
        if viol and strategy == "OPTIMIZER":
            continue
        violations += 1 if viol else 0
        opps.append({"id": c.id, "cost": pick["cost"], "expected_value": pick["expected_value"],
                     "expected_recovery": pick["expected_recovery"], "action": pick["action"], "p": pick["probability"],
                     "amount": c.revenue_at_risk, "needs_approval": pick["policy_status"] == ESCALATE})
    plan = E.allocate_budget(opps, budget)
    chosen = {i for i in plan["selected"]}
    sel = [o for o in opps if o["id"] in chosen]
    cost = sum(o["cost"] for o in sel)
    exp_rec = sum(o["expected_recovery"] for o in sel)
    if strategy == "DO_NOTHING":
        exp_rec = organic
    return {"label": "SIMULATION (estimated; not actual recovery)", "strategy": strategy, "segment": segment,
            "effective_contact_frequency": f, "budget": budget, "allocated": plan["allocated"], "remaining": plan["remaining"],
            "expected_recovery": round(exp_rec, 2), "estimated_cost": round(cost, 2),
            "expected_roi": round((exp_rec - cost) / cost, 2) if cost else None,
            "policy_violations": violations if strategy != "DO_NOTHING" else 0,
            "projected_recoveries": round(sum(o["p"] for o in sel), 1), "cases_targeted": len(sel),
            "cases_considered": len(opps), "top_allocations": sorted(sel, key=lambda o: -o["expected_value"])[:8]}
