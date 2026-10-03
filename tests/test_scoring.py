from conftest import ctx
from app.engine import score_recoverability, diagnose


def test_score_is_sum_of_explained_reasons():
    score, reasons = score_recoverability(ctx())
    assert score == max(1, min(99, 15 + sum(r["points"] for r in reasons)))
    assert all({"factor", "points", "text"} <= r.keys() for r in reasons)


def test_temporary_failure_scores_higher_than_hard_decline():
    t, _ = score_recoverability(ctx())
    h, _ = score_recoverability(ctx(failure_reason="card_expired", failure_class="HARD"))
    assert t > h


def test_fraud_flag_scores_lowest():
    f, _ = score_recoverability(ctx(failure_reason="suspected_fraud", failure_class="FRAUD"))
    t, _ = score_recoverability(ctx())
    assert f < t - 20


def test_payment_history_and_prior_recovery_raise_score():
    base, _ = score_recoverability(ctx(successful_payments=0))
    more, _ = score_recoverability(ctx(successful_payments=8, previous_recoveries=2))
    assert more > base


def test_stale_failure_and_overdue_age_lower_score():
    fresh, _ = score_recoverability(ctx(hours_since_failure=2))
    stale, _ = score_recoverability(ctx(hours_since_failure=900))
    assert stale < fresh
    a, _ = score_recoverability(ctx(source_type="invoice", failure_class="", days_overdue=3))
    b, _ = score_recoverability(ctx(source_type="invoice", failure_class="", days_overdue=45))
    assert b < a


def test_retries_and_contact_block_lower_score_and_clamped():
    a, _ = score_recoverability(ctx())
    b, _ = score_recoverability(ctx(retries_done=2, contact_allowed=False))
    assert b < a
    lo, _ = score_recoverability(ctx(failure_class="FRAUD", failure_reason="suspected_fraud", retries_done=2, failed_attempts=2,
                                     hours_since_failure=999, successful_payments=0, engagement=0.0, contact_allowed=False))
    assert 1 <= lo <= 99


def test_diagnosis_returns_root_cause_and_evidence():
    code, label, ev = diagnose(ctx())
    assert code == "TEMPORARY_FUNDS" and "Temporary" in label
    assert any("previous successful payments" in e for e in ev)
    code2, _, _ = diagnose(ctx(failure_reason="card_expired"))
    assert code2 == "CARD_EXPIRED"
