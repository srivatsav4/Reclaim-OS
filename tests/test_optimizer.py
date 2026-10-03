import pytest
from conftest import ctx
from app.engine import (allocate_budget, build_candidates, choose_action, inr, score_recoverability,
                        FRICTION_RATE, ACTION_META)


def run(**kw):
    c = ctx(**kw)
    s, _ = score_recoverability(c)
    cands = build_candidates(c, s)
    return c, cands, choose_action(cands, c)


def test_expected_recovery_is_amount_times_probability():
    _, cands, _ = run()
    for x in cands:
        assert x["expected_recovery"] == pytest.approx(20000 * x["probability"], abs=1.5)


def test_expected_value_subtracts_cost_and_friction():
    _, cands, _ = run()
    for x in cands:
        assert x["expected_value"] == pytest.approx(x["expected_recovery"] - x["cost"] - x["friction_penalty"], abs=0.02)
        assert x["cost"] == ACTION_META[x["action"]][0]


def test_high_ltv_raises_friction_penalty():
    _, lo, _ = run(ltv=1000)
    _, hi, _ = run(ltv=500000)
    p = lambda cs: next(x for x in cs if x["action"] == "PAYMENT_LINK")["friction_penalty"]
    assert p(hi) == pytest.approx(p(lo) * 1.5, abs=0.02)


def test_temporary_failure_selects_retry():
    _, _, ch = run()
    assert ch["decision"] == "ACT" and ch["selected"]["action"] == "RETRY_PAYMENT"


def test_hard_decline_selects_payment_link_not_retry():
    _, _, ch = run(failure_reason="card_expired", failure_class="HARD", amount=85000)
    assert ch["selected"]["action"] == "PAYMENT_LINK" and ch["decision"] == "ACT"
    assert ch["blocked_top"] is None or ch["blocked_top"]["action"] != "PAYMENT_LINK"


def test_chooses_best_permitted_not_best_unconstrained():
    _, cands, ch = run(retries_done=2)  # retry would otherwise win
    top = max((c for c in cands if c["action"] != "NO_ACTION"), key=lambda c: c["expected_value"])
    assert top["action"] == "RETRY_PAYMENT" and ch["blocked_top"]["action"] == "RETRY_PAYMENT"
    assert ch["selected"]["action"] != "RETRY_PAYMENT"


def test_already_resolved_is_no_action():
    _, _, ch = run(already_resolved=True)
    assert ch["decision"] == "NO_ACTION" and "already resolved" in ch["reason"].lower()


def test_everything_blocked_is_no_action_blocked():
    _, _, ch = run(retries_done=2, contact_allowed=False, amount=9900)
    assert ch["decision"] == "NO_ACTION" and ch["status_hint"] == "BLOCKED"


def test_tiny_amount_is_no_action_value_too_low():
    _, _, ch = run(amount=120)
    assert ch["decision"] == "NO_ACTION" and "too low" in ch["reason"]


def test_above_threshold_escalates_to_human():
    _, _, ch = run(source_type="invoice", failure_class="", amount=480000, promise_to_pay=True, days_overdue=21,
                   failure_reason=None, hours_since_failure=500)
    assert ch["decision"] == "ESCALATE" and ch["selected"]["policy_status"] == "ESCALATE"


def test_human_review_not_picked_when_cheap_automation_is_permitted():
    _, _, ch = run(amount=80000, source_type="invoice", failure_class="", days_overdue=12, failure_reason=None,
                   ltv=340000, hours_since_failure=288)
    assert ch["selected"]["action"] != "HUMAN_REVIEW"


def test_budget_allocation_example_fits_all():
    opps = [{"id": "A", "cost": 500, "expected_value": 29500, "expected_recovery": 30000},
            {"id": "B", "cost": 50, "expected_value": 6950, "expected_recovery": 7000},
            {"id": "C", "cost": 2000, "expected_value": 53000, "expected_recovery": 55000}]
    r = allocate_budget(opps, 10000)
    assert r["allocated"] == 2550 and r["remaining"] == 7450 and r["expected_recovery"] == 92000


def test_budget_allocation_prioritizes_by_value_per_cost():
    opps = [{"id": "A", "cost": 500, "expected_value": 29500, "expected_recovery": 30000},
            {"id": "B", "cost": 50, "expected_value": 6950, "expected_recovery": 7000},
            {"id": "C", "cost": 2000, "expected_value": 53000, "expected_recovery": 55000}]
    r = allocate_budget(opps, 1000)
    assert set(r["selected"]) == {"A", "B"} and r["skipped"] == ["C"] and r["allocated"] <= 1000


def test_budget_never_exceeded_and_zero_budget():
    opps = [{"id": i, "cost": 100, "expected_value": 1000 + i, "expected_recovery": 1100} for i in range(10)]
    assert allocate_budget(opps, 350)["allocated"] <= 350
    assert allocate_budget(opps, 0)["selected"] == []


def test_inr_indian_grouping():
    assert inr(118500) == "₹1,18,500" and inr(480000) == "₹4,80,000" and inr(999) == "₹999"
