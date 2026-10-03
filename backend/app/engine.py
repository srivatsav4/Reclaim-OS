"""Risk scoring, diagnosis, candidate generation, expected-value optimizer and budget allocation.
All logic is deterministic and explainable (AI_MODE=demo). An LLM could be plugged in behind `explain()`."""
from .policy import (ALLOW, BLOCK, ESCALATE, CHECKOUT_RECOVERY, CUSTOMER_EMAIL, CUSTOMER_NOTIFICATION,
                     HUMAN_REVIEW, INVOICE_REMINDER, NO_ACTION, PAYMENT_LINK, PROMISE_TO_PAY_FOLLOWUP,
                     RETRY_PAYMENT, Policy, evaluate)

FAILURE_CLASS = {"insufficient_funds": "TEMPORARY", "issuer_unavailable": "TEMPORARY", "network_timeout": "TEMPORARY",
                 "bank_declined_temporary": "TEMPORARY", "authentication_failed": "AUTH", "card_expired": "HARD",
                 "do_not_honor": "HARD", "suspected_fraud": "FRAUD"}
ROOT_CAUSES = {
    "insufficient_funds": ("TEMPORARY_FUNDS", "Temporary payment failure (insufficient funds)"),
    "issuer_unavailable": ("TEMPORARY_ISSUER", "Temporary payment failure (issuer unavailable)"),
    "network_timeout": ("TEMPORARY_NETWORK", "Temporary payment failure (network timeout)"),
    "bank_declined_temporary": ("TEMPORARY_DECLINE", "Temporary payment failure (soft bank decline)"),
    "authentication_failed": ("AUTH_FAILURE", "Authentication failure (3DS/OTP not completed)"),
    "card_expired": ("CARD_EXPIRED", "Expired payment instrument"),
    "do_not_honor": ("HARD_DECLINE", "Hard decline by issuer"),
    "suspected_fraud": ("FRAUD_SUSPECTED", "Suspected-fraud flag on payment"),
}
# action -> (cost INR, friction level)
ACTION_META = {
    RETRY_PAYMENT: (20, "low"), PAYMENT_LINK: (10, "low"), CHECKOUT_RECOVERY: (12, "low"),
    CUSTOMER_EMAIL: (5, "low"), CUSTOMER_NOTIFICATION: (2, "low"), INVOICE_REMINDER: (8, "medium"),
    PROMISE_TO_PAY_FOLLOWUP: (15, "medium"), HUMAN_REVIEW: (250, "high"), NO_ACTION: (0, "none"),
}
FRICTION_RATE = {"none": 0.0, "low": 0.004, "medium": 0.012, "high": 0.08}
BASE = {
    "TEMPORARY": {RETRY_PAYMENT: .60, PAYMENT_LINK: .52, CUSTOMER_EMAIL: .30, CUSTOMER_NOTIFICATION: .24, HUMAN_REVIEW: .45, NO_ACTION: .22},
    "AUTH": {RETRY_PAYMENT: .12, PAYMENT_LINK: .56, CUSTOMER_EMAIL: .32, CUSTOMER_NOTIFICATION: .26, HUMAN_REVIEW: .45, NO_ACTION: .15},
    "HARD": {RETRY_PAYMENT: .03, PAYMENT_LINK: .55, CUSTOMER_EMAIL: .34, CUSTOMER_NOTIFICATION: .27, HUMAN_REVIEW: .50, NO_ACTION: .10},
    "FRAUD": {RETRY_PAYMENT: .02, PAYMENT_LINK: .18, CUSTOMER_EMAIL: .14, CUSTOMER_NOTIFICATION: .10, HUMAN_REVIEW: .40, NO_ACTION: .03},
    "CHECKOUT": {CHECKOUT_RECOVERY: .30, CUSTOMER_EMAIL: .18, CUSTOMER_NOTIFICATION: .14, HUMAN_REVIEW: .22, NO_ACTION: .08},
    "INVOICE": {INVOICE_REMINDER: .42, PAYMENT_LINK: .46, CUSTOMER_EMAIL: .30, HUMAN_REVIEW: .55, NO_ACTION: .15},
    "INVOICE_PROMISE": {PROMISE_TO_PAY_FOLLOWUP: .62, INVOICE_REMINDER: .44, PAYMENT_LINK: .48, CUSTOMER_EMAIL: .32,
                        HUMAN_REVIEW: .58, NO_ACTION: .20},
}
APPLICABLE = {
    "payment": [RETRY_PAYMENT, PAYMENT_LINK, CUSTOMER_EMAIL, CUSTOMER_NOTIFICATION, HUMAN_REVIEW, NO_ACTION],
    "subscription": [RETRY_PAYMENT, PAYMENT_LINK, CUSTOMER_EMAIL, CUSTOMER_NOTIFICATION, HUMAN_REVIEW, NO_ACTION],
    "checkout": [CHECKOUT_RECOVERY, CUSTOMER_EMAIL, CUSTOMER_NOTIFICATION, HUMAN_REVIEW, NO_ACTION],
    "invoice": [INVOICE_REMINDER, PAYMENT_LINK, CUSTOMER_EMAIL, HUMAN_REVIEW, NO_ACTION],
}


def inr(x: float) -> str:
    """Indian digit grouping, e.g. 118500 -> ₹1,18,500."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def classify(ctx: dict) -> str:
    st = ctx["source_type"]
    if st == "checkout":
        return "CHECKOUT"
    if st == "invoice":
        return "INVOICE_PROMISE" if ctx.get("promise_to_pay") else "INVOICE"
    return FAILURE_CLASS.get(ctx.get("failure_reason"), "TEMPORARY")


def failure_class(ctx: dict) -> str:
    return FAILURE_CLASS.get(ctx.get("failure_reason"), "") if ctx["source_type"] in ("payment", "subscription") else ""


# ---------------------------------------------------------------- scoring
def score_recoverability(ctx: dict):
    """Explainable additive score in [1, 99]. Returns (score, reasons[{factor, points, text}])."""
    reasons = []

    def add(factor, pts, text):
        pts = int(round(pts))
        if pts:
            reasons.append({"factor": factor, "points": pts, "text": text})

    base = 15
    sp = ctx.get("successful_payments", 0)
    if sp > 0:
        add("payment_history", min(18, sp * 2.5), f"{sp} previous successful payments")
    else:
        add("payment_history", -6, "No successful payment history")

    fc, st = failure_class(ctx), ctx["source_type"]
    if fc == "TEMPORARY":
        add("failure_type", 14, "Temporary payment failure")
    elif fc == "AUTH":
        add("failure_type", 5, "Authentication failure (customer can complete it)")
    elif fc == "HARD":
        add("failure_type", -6, "Hard decline / expired instrument")
    elif fc == "FRAUD":
        add("failure_type", -22, "Suspected fraud flag")
    elif st == "checkout":
        add("failure_type", 6, "Checkout intent signal (items were in cart)")
    elif st == "invoice" and ctx.get("promise_to_pay"):
        add("failure_type", 10, "Customer made a promise-to-pay")

    ltv = ctx.get("ltv", 0)
    add("customer_value", 8 if ltv >= 200000 else 5 if ltv >= 50000 else 1,
        "High customer lifetime value" if ltv >= 50000 else "Modest customer lifetime value")

    h = ctx.get("hours_since_failure", 0)
    add("recency", 12 if h < 24 else 8 if h < 72 else 3 if h < 168 else -3 if h <= 720 else -10,
        f"Failure occurred {h}h ago" if h < 168 else f"Stale failure ({h // 24} days ago)")

    pr = ctx.get("previous_recoveries", 0)
    if pr:
        add("previous_recovery", min(10, pr * 5), f"{pr} previous successful recoveries")

    od = ctx.get("days_overdue", 0)
    if od > 30:
        add("overdue_age", -15, f"{od} days overdue")
    elif od > 14:
        add("overdue_age", -9, f"{od} days overdue")
    elif od > 7:
        add("overdue_age", -4, f"{od} days overdue")

    eng = ctx.get("engagement", 0.5)
    add("engagement", (eng - 0.4) * 25, "Strong customer engagement" if eng >= 0.6 else "Low customer engagement")

    rd = ctx.get("retries_done", 0)
    if rd:
        add("retry_count", -8 * rd, f"{rd} previous retries used")
    fa = ctx.get("failed_attempts", 0)
    if fa:
        add("failed_attempts", -10 * fa, f"{fa} failed recovery attempts")
    if not ctx.get("contact_allowed", True):
        add("contact_permission", -6, "Contact not permitted; outreach channels closed")
    seg = ctx.get("segment")
    if seg == "Enterprise":
        add("segment", 4, "Enterprise segment")
    elif seg == "Consumer":
        add("segment", -2, "Consumer segment")
    pm = ctx.get("payment_method")
    if pm == "upi":
        add("payment_method", 3, "UPI (fast to re-attempt)")
    elif pm == "emi":
        add("payment_method", -4, "EMI instrument (limit-bound)")
    if st == "checkout" and ctx.get("amount", 0) > 30000:
        add("checkout_value", -3, "Large cart; higher hesitation")

    score = max(1, min(99, base + sum(r["points"] for r in reasons)))
    return int(score), reasons


# ---------------------------------------------------------------- diagnosis
def diagnose(ctx: dict):
    st = ctx["source_type"]
    ev = []
    if st in ("payment", "subscription"):
        code, label = ROOT_CAUSES.get(ctx.get("failure_reason"), ("UNKNOWN", "Unclassified payment failure"))
        if st == "subscription":
            label = label.replace("payment failure", "renewal failure")
    elif st == "checkout":
        code, label = "CHECKOUT_ABANDONED", f"Abandoned checkout ({ctx.get('abandon_reason', 'unknown reason').replace('_', ' ')})"
    else:
        code = "OVERDUE_PROMISE" if ctx.get("promise_to_pay") else "OVERDUE_INVOICE"
        label = "Overdue invoice with promise-to-pay" if ctx.get("promise_to_pay") else "Overdue invoice"
    sp = ctx.get("successful_payments", 0)
    ev.append(f"{sp} previous successful payments" if sp else "No successful payment history")
    h = ctx.get("hours_since_failure", 0)
    ev.append(f"Failure occurred {h}h ago" if h < 168 else f"Failure is {h // 24} days old")
    if ctx.get("retries_done"):
        ev.append(f"{ctx['retries_done']} retries already used")
    if ctx.get("days_overdue"):
        ev.append(f"Invoice is {ctx['days_overdue']} days overdue")
    ev.append("Customer contact allowed" if ctx.get("contact_allowed", True) else "Customer contact NOT allowed")
    ev.append("Prior successful recovery on record" if ctx.get("previous_recoveries") else "No previous recovery abuse")
    if ctx.get("already_resolved"):
        ev.append("Customer has already resolved this item")
    return code, label, ev


# ---------------------------------------------------------------- candidates / optimizer
def retry_delay_factor(hours: float) -> float:
    return 0.7 if hours < 6 else 1.0 if hours <= 72 else 0.85 if hours <= 120 else 0.7


def build_candidates(ctx: dict, score: int, policy: Policy | None = None) -> list:
    policy = policy or Policy()
    amount = ctx["amount"]
    cls = classify(ctx)
    table = BASE[cls]
    actions = list(APPLICABLE[ctx["source_type"]])
    if ctx["source_type"] == "invoice" and ctx.get("promise_to_pay"):
        actions.insert(0, PROMISE_TO_PAY_FOLLOWUP)
    factor = 0.55 + 0.9 * score / 100
    mult = 1.5 if ctx.get("ltv", 0) >= 200000 else 1.0
    out = []
    for a in actions:
        base = table.get(a, 0.10)
        p = min(0.5, base * (0.6 + 0.8 * score / 100)) if a == NO_ACTION else min(0.95, base * factor)
        if a == HUMAN_REVIEW:
            p *= 0.9  # approval latency discount
        if a == RETRY_PAYMENT:
            p *= retry_delay_factor(ctx.get("retry_delay_hours", 48))
        cost, fr = ACTION_META[a]
        expected = amount * p
        penalty = amount * FRICTION_RATE[fr] * mult
        pr = evaluate(a, ctx, policy)
        out.append({"action": a, "probability": round(p, 4), "expected_recovery": round(expected, 2), "cost": cost,
                    "friction": fr, "friction_penalty": round(penalty, 2),
                    "expected_value": round(expected - cost - penalty, 2),
                    "policy_status": pr.status, "policy_reasons": pr.reasons, "policy_rules": pr.rules,
                    "risk_level": {"low": "LOW", "medium": "MEDIUM", "high": "MEDIUM", "none": "LOW"}[fr]})
    return out


def choose_action(cands: list, ctx: dict, policy: Policy | None = None) -> dict:
    """Pick the highest-EV PERMITTED action. NO_ACTION is a first-class outcome."""
    policy = policy or Policy()
    noop = next(c for c in cands if c["action"] == NO_ACTION)
    real = [c for c in cands if c["action"] != NO_ACTION]
    top = max(real, key=lambda c: c["expected_value"])
    blocked_top = top if top["policy_status"] == BLOCK else None
    permitted = [c for c in real if c["policy_status"] in (ALLOW, ESCALATE)]
    base = {"blocked_top": blocked_top, "noop": noop}
    if ctx.get("already_resolved"):
        return {**base, "decision": "NO_ACTION", "selected": noop, "status_hint": "NO_ACTION",
                "reason": top["policy_reasons"][0]}
    if not permitted:
        why = top["policy_reasons"][0]
        return {**base, "decision": "NO_ACTION", "selected": noop, "status_hint": "BLOCKED",
                "reason": f"Every recovery action is blocked by policy. Top option blocked: {why}"}
    best = max(permitted, key=lambda c: c["expected_value"])
    if best["expected_value"] - noop["expected_value"] < policy.MIN_NET_GAIN:
        return {**base, "decision": "NO_ACTION", "selected": noop, "status_hint": "NO_ACTION",
                "reason": f"Recovery value too low: best action nets only {inr(best['expected_value'] - noop['expected_value'])} "
                          f"over doing nothing (minimum {inr(policy.MIN_NET_GAIN)})"}
    if best["policy_status"] == ESCALATE:
        return {**base, "decision": "ESCALATE", "selected": best, "status_hint": "ESCALATED",
                "reason": best["policy_reasons"][0]}
    return {**base, "decision": "ACT", "selected": best, "status_hint": "ANALYZED",
            "reason": "Highest expected value among permitted actions after cost, friction and policy constraints"}


def priority_for(amount: float, hours: float) -> str:
    if amount >= 100000:
        return "CRITICAL"
    if amount >= 50000 or (amount >= 20000 and hours < 48):
        return "HIGH"
    return "MEDIUM" if amount >= 10000 else "LOW"


def explain(ctx: dict, score: int, root_label: str, evidence: list, choice: dict, policy: Policy) -> dict:
    sel = choice["selected"]
    why_case = [f"Revenue at risk: {inr(ctx['amount'])}", f"Root cause: {root_label}"] + evidence
    if choice["decision"] == "ACT":
        why_action = [f"Highest expected permitted value ({inr(sel['expected_value'])} net of cost and friction)",
                      f"Customer friction is {sel['friction']}", "Within policy; no human approval required"]
    elif choice["decision"] == "ESCALATE":
        why_action = [f"Best expected action is {sel['action']} but policy requires a human: {choice['reason']}"]
    else:
        why_action = [choice["reason"]]
    stop = (f"Stop after successful payment or {policy.MAX_FAILED_RECOVERY_ATTEMPTS} failed recovery attempts; "
            f"never exceed {policy.MAX_CUSTOMER_MESSAGES} customer messages or {policy.MAX_PAYMENT_RETRIES} retries.")
    return {"why_case": why_case, "why_action": why_action, "stopping_condition": stop, "mode": "demo"}


# ---------------------------------------------------------------- budget
def allocate_budget(opps: list, budget: float) -> dict:
    """Greedy allocation by expected value per rupee of intervention cost (an approximation of the 0/1 knapsack)."""
    ranked = sorted([o for o in opps if o["expected_value"] > 0],
                    key=lambda o: o["expected_value"] / max(o["cost"], 1.0), reverse=True)
    remaining, chosen, skipped, exp = float(budget), [], [], 0.0
    for o in ranked:
        if o["cost"] <= remaining:
            remaining -= o["cost"]
            chosen.append(o["id"])
            exp += o["expected_recovery"]
        else:
            skipped.append(o["id"])
    return {"budget": float(budget), "allocated": round(float(budget) - remaining, 2), "remaining": round(remaining, 2),
            "expected_recovery": round(exp, 2), "selected": chosen, "skipped": skipped}
