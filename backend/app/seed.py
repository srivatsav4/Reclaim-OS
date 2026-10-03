"""Deterministic demo seed. Everything here is synthetic: DEMO / SIMULATED."""
from datetime import timedelta

import numpy as np
from sqlalchemy import select

from . import service as svc
from . import simulator as S
from .db import Base, engine, utcnow
from .models import (Checkout, Customer, HumanReview, Invoice, Payment, RecoveryCase, RecoveryPolicy, Subscription)
from .policy import POLICY_DESCRIPTIONS, Policy

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Siddharth", "Ishaan", "Rahul", "Nikhil", "Varun", "Kabir",
         "Ananya", "Diya", "Priya", "Neha", "Kavya", "Meera", "Sneha", "Pooja", "Riya", "Isha", "Aditi", "Lakshmi", "Divya",
         "Sanjay", "Manoj", "Suresh", "Ramesh", "Anil", "Vikram", "Deepak", "Harish", "Gopal", "Mohan", "Naveen", "Praveen",
         "Shreya", "Tanvi", "Swati", "Anjali", "Pallavi", "Rekha", "Sunita", "Jyoti", "Nandini", "Bhavna", "Tara", "Zoya", "Imran"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Naidu", "Patel", "Shah", "Mehta", "Gupta", "Agarwal", "Kapoor", "Malhotra",
        "Chopra", "Singh", "Kumar", "Das", "Banerjee", "Chatterjee", "Mukherjee", "Menon", "Pillai", "Rao", "Hegde", "Kulkarni",
        "Joshi", "Desai", "Bhatt", "Thakur", "Yadav", "Pandey", "Mishra", "Khan", "Ansari", "Fernandes", "D'Souza", "Gill", "Sandhu",
        "Subramanian", "Venkatesh", "Krishnan", "Raman", "Bose", "Sen", "Ghosh", "Jain", "Saxena", "Tiwari", "Chaudhary", "Kaur"]
REASONS = ["insufficient_funds", "issuer_unavailable", "network_timeout", "bank_declined_temporary",
           "authentication_failed", "card_expired", "do_not_honor", "suspected_fraud"]
REASON_W = np.array([.30, .08, .07, .10, .11, .20, .10, .04])
ABANDON = ["payment_page_exit", "shipping_cost_shock", "otp_timeout", "coupon_failed", "compared_prices", "session_expired"]
SEGMENTS = ["Consumer", "SMB", "Mid-Market", "Enterprise"]

SCENARIOS = [
    {"key": "S1_RETRY_SUCCESS", "title": "₹18,500 temporary failure → retry", "expected": "RETRY_PAYMENT → SUCCESS",
     "description": "Temporary insufficient-funds failure for a loyal customer. The optimizer picks a payment retry."},
    {"key": "S2_LINK_SUCCESS", "title": "₹85,000 high-value failure → payment link", "expected": "PAYMENT_LINK → SUCCESS",
     "description": "Expired card, so retry is not retryable. A payment link is the best permitted action, below the approval threshold."},
    {"key": "S3_HUMAN_ESCALATION", "title": "₹4,80,000 overdue invoice → human escalation", "expected": "ESCALATE (above approval threshold)",
     "description": "Above the ₹1,00,000 human approval threshold, so the policy gate routes it to a human."},
    {"key": "S4_ALREADY_PAID", "title": "Customer already paid → NO ACTION", "expected": "NO_ACTION",
     "description": "The customer settled this payment through another channel. Safe agents do nothing."},
    {"key": "S5_RETRY_LIMIT", "title": "Retry limit exceeded → BLOCKED", "expected": "BLOCKED (NO_ACTION)",
     "description": "Two retries already used and contact is not permitted; every action is blocked by policy."},
    {"key": "S6_CHECKOUT_RECOVERY", "title": "Abandoned checkout → checkout recovery", "expected": "CHECKOUT_RECOVERY → SUCCESS",
     "description": "An abandoned ₹6,400 cart is recovered with a checkout-recovery nudge."},
]


def seed(db, rng_seed: int = 42, split: float = 0.7, ai_seed: int = 42) -> dict:
    rng = np.random.default_rng(rng_seed)
    now = utcnow()
    for k, v in Policy().as_dict().items():
        db.add(RecoveryPolicy(key=k, value=float(v), description=POLICY_DESCRIPTIONS[k]))

    # ---------------- scenario customers (fixed, hand-built)
    def mk_customer(name, seg, ltv, eng, succ, prev, contact=True, email=None):
        c = Customer(name=name, email=email or f"{name.lower().replace(' ', '.')}@example.com", segment=seg, lifetime_value=ltv,
                     created_at=now - timedelta(days=540), preferred_channel="email", contact_allowed=contact,
                     risk_level="LOW", successful_payments=succ, previous_recoveries=prev, engagement=eng)
        db.add(c)
        db.flush()
        return c

    sc = {
        "aarav": mk_customer("Aarav Sharma", "Mid-Market", 340000, .82, 7, 1),
        "meera": mk_customer("Meera Nair", "Enterprise", 620000, .74, 11, 1),
        "vikram": mk_customer("Vikram Industries Pvt Ltd", "Enterprise", 1850000, .66, 22, 2, email="accounts@vikram-industries.example.com"),
        "ananya": mk_customer("Ananya Reddy", "SMB", 64000, .7, 6, 0),
        "rohit": mk_customer("Rohit Malhotra", "Consumer", 21000, .35, 3, 0, contact=False),
        "neha": mk_customer("Neha Iyer", "Consumer", 28000, .68, 5, 0),
    }
    cases_meta = []  # (customer_id, source_type, source_id, amount, ctx, scenario, hours)

    def add_pay(cu, amt, reason, method="card", retries=0, status="FAILED", hours=6):
        p = Payment(customer_id=cu.id, amount=amt, status=status, failure_reason=reason, payment_method=method,
                    attempt_number=retries + 1, created_at=now - timedelta(hours=hours))
        db.add(p)
        db.flush()
        return p

    def ctx_pay(p, hours, retries=0, msgs=0, last=None, **kw):
        return {"failure_reason": p.failure_reason, "payment_method": p.payment_method, "retries_done": retries,
                "failed_attempts": 0, "messages_sent": msgs, "last_message_hours_ago": last,
                "hours_since_failure": hours, "already_resolved": False, **kw}

    p = add_pay(sc["aarav"], 18500, "insufficient_funds", "upi", hours=5)
    cases_meta.append((sc["aarav"].id, "payment", p.id, 18500, ctx_pay(p, 5, forced_outcome="SUCCESS"), "S1_RETRY_SUCCESS", 5))
    ck = Checkout(customer_id=sc["aarav"].id, cart_value=18000, status="ABANDONED", started_at=now - timedelta(hours=30),
                  abandoned_at=now - timedelta(hours=29), device="mobile", channel="app")
    sb = Subscription(customer_id=sc["aarav"].id, amount=2000, billing_cycle="monthly", status="PAST_DUE",
                      next_billing_date=now + timedelta(days=2), failure_count=1)
    iv = Invoice(customer_id=sc["aarav"].id, amount=80000, due_date=now - timedelta(days=12), status="OVERDUE", days_overdue=12)
    db.add_all([ck, sb, iv])
    db.flush()
    cases_meta += [
        (sc["aarav"].id, "checkout", ck.id, 18000, {"abandon_reason": "payment_page_exit", "hours_since_failure": 29, "messages_sent": 0,
                                                  "last_message_hours_ago": None, "failed_attempts": 0, "already_resolved": False}, "S1_GRAPH", 29),
        (sc["aarav"].id, "subscription", sb.id, 2000, {"failure_reason": "network_timeout", "payment_method": "card", "retries_done": 0,
                                                     "failed_attempts": 0, "messages_sent": 0, "last_message_hours_ago": None,
                                                     "hours_since_failure": 20, "already_resolved": False}, "S1_GRAPH", 20),
        (sc["aarav"].id, "invoice", iv.id, 80000, {"days_overdue": 12, "promise_to_pay": False, "messages_sent": 1,
                                                 "last_message_hours_ago": 96, "failed_attempts": 0, "hours_since_failure": 288,
                                                 "already_resolved": False}, "S1_GRAPH", 288)]
    p = add_pay(sc["meera"], 85000, "card_expired", "card", hours=18)
    cases_meta.append((sc["meera"].id, "payment", p.id, 85000, ctx_pay(p, 18, forced_outcome="SUCCESS"), "S2_LINK_SUCCESS", 18))
    iv = Invoice(customer_id=sc["vikram"].id, amount=480000, due_date=now - timedelta(days=21), status="OVERDUE", days_overdue=21,
                 promise_to_pay_date=now + timedelta(days=5))
    db.add(iv)
    db.flush()
    cases_meta.append((sc["vikram"].id, "invoice", iv.id, 480000, {"days_overdue": 21, "promise_to_pay": True, "messages_sent": 1,
                                                                 "last_message_hours_ago": 120, "failed_attempts": 0,
                                                                 "hours_since_failure": 504, "already_resolved": False,
                                                                 "forced_outcome": "SUCCESS"}, "S3_HUMAN_ESCALATION", 504))
    p = add_pay(sc["ananya"], 12400, "insufficient_funds", "upi", status="RESOLVED", hours=30)
    cases_meta.append((sc["ananya"].id, "payment", p.id, 12400, ctx_pay(p, 30, already_resolved=True), "S4_ALREADY_PAID", 30))
    p = add_pay(sc["rohit"], 9900, "insufficient_funds", "card", retries=2, hours=60)
    cases_meta.append((sc["rohit"].id, "payment", p.id, 9900, ctx_pay(p, 60, retries=2, msgs=1, last=70), "S5_RETRY_LIMIT", 60))
    ck = Checkout(customer_id=sc["neha"].id, cart_value=6400, status="ABANDONED", started_at=now - timedelta(hours=9),
                  abandoned_at=now - timedelta(hours=8), device="mobile", channel="web")
    db.add(ck)
    db.flush()
    cases_meta.append((sc["neha"].id, "checkout", ck.id, 6400, {"abandon_reason": "otp_timeout", "hours_since_failure": 8, "messages_sent": 0,
                                                             "last_message_hours_ago": None, "failed_attempts": 0, "already_resolved": False,
                                                             "forced_outcome": "SUCCESS"}, "S6_CHECKOUT_RECOVERY", 8))

    # ---------------- 1000 generated customers
    segs = rng.choice(SEGMENTS, size=1000, p=[.45, .35, .13, .07])
    mu = {"Consumer": 9.4, "SMB": 11.0, "Mid-Market": 12.1, "Enterprise": 13.0}
    custs = []
    for i in range(1000):
        fn, ln = FIRST[rng.integers(len(FIRST))], LAST[rng.integers(len(LAST))]
        eng = float(np.clip(rng.beta(5, 3), 0.05, 0.98))
        c = Customer(name=f"{fn} {ln}", email=f"{fn}.{ln}.{i}@example.com".lower().replace("'", ""), segment=str(segs[i]),
                     lifetime_value=float(round(rng.lognormal(mu[str(segs[i])], .55), -2)),
                     created_at=now - timedelta(days=int(rng.integers(30, 1200))),
                     preferred_channel=str(rng.choice(["email", "sms", "whatsapp", "push"], p=[.35, .25, .3, .1])),
                     contact_allowed=bool(rng.random() < .93), engagement=round(eng, 2),
                     risk_level="HIGH" if eng < .4 else "MEDIUM" if eng < .6 else "LOW")
        custs.append(c)
    db.add_all(custs)
    db.flush()
    cids = [c.id for c in custs]
    pool = [int(x) for x in rng.choice(cids, size=130, replace=False)]

    # ---------------- payments
    methods = ["card", "upi", "netbanking", "emi"]
    mw = [.5, .3, .12, .08]
    pays = []
    for _ in range(1200):
        pays.append(Payment(customer_id=int(rng.choice(cids)), amount=float(np.clip(round(rng.lognormal(8.4, .9), 0), 99, 60000)),
                            status="SUCCEEDED", payment_method=str(rng.choice(methods, p=mw)),
                            created_at=now - timedelta(days=int(rng.integers(1, 90)), hours=int(rng.integers(0, 24)))))
    for _ in range(240):  # failed then resolved by the customer / auto-retry
        h = int(rng.integers(24, 2000))
        pays.append(Payment(customer_id=int(rng.choice(cids)), amount=float(np.clip(round(rng.lognormal(8.6, .9), 0), 150, 80000)),
                            status="RESOLVED", failure_reason=str(rng.choice(REASONS, p=REASON_W / REASON_W.sum())),
                            payment_method=str(rng.choice(methods, p=mw)), attempt_number=int(rng.integers(2, 4)),
                            created_at=now - timedelta(hours=h), resolved_at=now - timedelta(hours=max(1, h - 20))))
    db.add_all(pays)

    # ---------------- open at-risk items
    def hours():
        return int(np.clip(rng.exponential(110), 2, 330)) if rng.random() < .9 else int(rng.integers(340, 760))

    def msgs():
        m = int(rng.choice([0, 1, 2, 3], p=[.55, .25, .12, .08]))
        return m, (None if m == 0 else int(rng.integers(6, 200)))

    for _ in range(90):
        cid, h = int(rng.choice(pool)), hours()
        amt = float(np.clip(round(rng.lognormal(9.1, 1.0), -1), 600, 260000))
        res = bool(rng.random() < .04)
        reason = str(rng.choice(REASONS, p=REASON_W / REASON_W.sum()))
        retries = int(rng.choice([0, 1, 2], p=[.6, .28, .12]))
        pm = str(rng.choice(methods, p=mw))
        pay = Payment(customer_id=cid, amount=amt, status="RESOLVED" if res else "FAILED", failure_reason=reason, payment_method=pm,
                      attempt_number=retries + 1, created_at=now - timedelta(hours=h))
        db.add(pay)
        db.flush()
        m, last = msgs()
        cases_meta.append((cid, "payment", pay.id, amt, ctx_pay(pay, h, retries, m, last, already_resolved=res), None, h))
    chk = []
    for i in range(320):
        cid = int(rng.choice(pool)) if i < 45 else int(rng.choice(cids))
        aband = i < 130
        cv = float(np.clip(round(rng.lognormal(8.6, .8), -1), 400, 90000))
        h = hours()
        ck = Checkout(customer_id=cid, cart_value=cv, status="ABANDONED" if aband else "COMPLETED",
                      started_at=now - timedelta(hours=h + 1), abandoned_at=now - timedelta(hours=h) if aband else None,
                      device=str(rng.choice(["mobile", "desktop", "tablet"], p=[.6, .33, .07])), channel=str(rng.choice(["web", "app"])))
        db.add(ck)
        if i < 45:
            db.flush()
            m, last = msgs()
            res = bool(rng.random() < .04)
            if res:
                ck.status = "RESOLVED"
            cases_meta.append((cid, "checkout", ck.id, cv, {"abandon_reason": str(rng.choice(ABANDON)), "hours_since_failure": h,
                                                           "messages_sent": min(m, 1), "last_message_hours_ago": last if m else None,
                                                           "failed_attempts": 0, "already_resolved": res}, None, h))
    for i in range(220):
        cid = int(rng.choice(pool)) if i < 22 else int(rng.choice(cids))
        past = i < 22
        amt = float(rng.choice([149, 299, 499, 999, 1999, 2999, 4999, 9999, 24999]))
        sb = Subscription(customer_id=cid, amount=amt, billing_cycle=str(rng.choice(["monthly", "quarterly", "annual"], p=[.7, .2, .1])),
                          status="PAST_DUE" if past else "ACTIVE", next_billing_date=now + timedelta(days=int(rng.integers(1, 30))),
                          failure_count=int(rng.integers(1, 3)) if past else 0)
        db.add(sb)
        if past:
            db.flush()
            h = hours()
            m, last = msgs()
            cases_meta.append((cid, "subscription", sb.id, amt, {"failure_reason": str(rng.choice(REASONS[:6], p=REASON_W[:6] / REASON_W[:6].sum())),
                                                                "payment_method": str(rng.choice(methods, p=mw)), "retries_done": sb.failure_count - 1,
                                                                "failed_attempts": 0, "messages_sent": m, "last_message_hours_ago": last,
                                                                "hours_since_failure": h, "already_resolved": False}, None, h))
    for i in range(160):
        cid = int(rng.choice(pool)) if i < 30 else int(rng.choice(cids))
        over = i < 30
        amt = float(np.clip(round(rng.lognormal(10.6, 1.0), -2), 3000, 450000))
        od = int(np.clip(rng.exponential(15), 1, 70))
        iv = Invoice(customer_id=cid, amount=amt, due_date=now - timedelta(days=od if over else int(rng.integers(5, 40))),
                     status="OVERDUE" if over else "PAID", days_overdue=od if over else 0,
                     promise_to_pay_date=(now + timedelta(days=int(rng.integers(1, 12)))) if over and rng.random() < .3 else None)
        db.add(iv)
        if over:
            db.flush()
            m, last = msgs()
            res = bool(rng.random() < .04)
            if res:
                iv.status = "PAID"
            cases_meta.append((cid, "invoice", iv.id, amt, {"days_overdue": od, "promise_to_pay": iv.promise_to_pay_date is not None,
                                                           "messages_sent": m, "last_message_hours_ago": last, "failed_attempts": 0,
                                                           "hours_since_failure": od * 24, "already_resolved": res}, None, od * 24))
    db.flush()

    # ---------------- customer history counters
    from sqlalchemy import func
    cnt = dict(db.execute(select(Payment.customer_id, func.count()).where(Payment.status.in_(["SUCCEEDED", "RESOLVED"])).group_by(Payment.customer_id)).all())
    fixed = {c.id for c in sc.values()}
    for c in custs:
        c.successful_payments = int(cnt.get(c.id, 0)) + int(rng.integers(0, 6))
        c.previous_recoveries = int(rng.poisson(.35)) if c.id in pool else 0
    db.flush()

    # ---------------- cases: create, audit, analyze
    cases = []
    for cid, st, sid, amt, ctx, scen, h in cases_meta:
        created = now - timedelta(hours=h)
        case = RecoveryCase(customer_id=cid, source_type=st, source_id=sid, revenue_at_risk=amt, context=ctx, scenario=scen,
                            status="OPEN", created_at=created, updated_at=created)
        db.add(case)
        db.flush()
        svc.audit(db, "CASE_CREATED", "INGESTION", f"{st} at risk: ₹{amt:,.0f} (DEMO / SIMULATED)", case=case, at=created,
                  meta={"source": st, "source_id": sid})
        svc.analyze_case(db, case, at=created + timedelta(minutes=15), first=True)
        cases.append(case)

    # ---------------- AI vs control assignment and historical execution
    for c in cases:
        if c.scenario:
            c.group = "DEMO"
            continue
        t0 = c.created_at + timedelta(minutes=40 + int(S.unit(c.id, "lag") * 300))
        t0 = min(t0, now - timedelta(minutes=10))
        if c.experiment_eligible:
            c.group = S.assign_group(c.id, ai_seed, split)
            if c.group == "AI":
                if c.id % 11 != 0:
                    svc.execute_case(db, c.id, at=t0)
            else:
                rec = S.simulate_control(c.id, c.baseline["organic_p"])
                c.status, c.organic_recovery = ("CONTROL_RECOVERED", c.revenue_at_risk) if rec else ("CONTROL_HOLD", 0.0)
                svc.audit(db, "NO_ACTION_SELECTED", "EXPERIMENT_ENGINE", "Held out in the control group (simulated experiment): "
                          "no automated recovery action", case=c, at=t0, outcome=c.status)
        elif c.decision == "ESCALATE":
            c.group = "AI"
            u = S.unit(c.id, "review")
            if u < .30:
                svc.approve_case(db, c.id, by="demo_reviewer", note="Approved in demo history", at=t0 + timedelta(hours=2))
            elif u < .45:
                svc.reject_case(db, c.id, by="demo_reviewer", note="Rejected in demo history", at=t0 + timedelta(hours=2))
    db.flush()
    svc.run_experiment(db, split=split, seed=ai_seed)
    db.commit()
    return {"customers": len(custs) + len(sc), "cases": len(cases)}


def reset_demo(db) -> dict:
    db.rollback()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return seed(db)
