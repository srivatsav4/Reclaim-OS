from conftest import ctx
from app.policy import (Policy, evaluate, ALLOW, BLOCK, ESCALATE, RETRY_PAYMENT, PAYMENT_LINK, CUSTOMER_EMAIL,
                        HUMAN_REVIEW, NO_ACTION)


def test_clean_case_is_allowed():
    assert evaluate(RETRY_PAYMENT, ctx()).status == ALLOW


def test_retry_limit_blocks_retry():
    r = evaluate(RETRY_PAYMENT, ctx(retries_done=2))
    assert r.status == BLOCK and "MAX_PAYMENT_RETRIES" in r.rules


def test_retry_allowed_at_one_used():
    assert evaluate(RETRY_PAYMENT, ctx(retries_done=1)).status == ALLOW


def test_non_retryable_failure_blocks_retry_but_not_link():
    c = ctx(failure_class="HARD", failure_reason="card_expired")
    assert evaluate(RETRY_PAYMENT, c).status == BLOCK
    assert evaluate(PAYMENT_LINK, c).status == ALLOW


def test_contact_permission_blocks_all_contact_actions():
    c = ctx(contact_allowed=False)
    assert evaluate(PAYMENT_LINK, c).status == BLOCK
    assert evaluate(CUSTOMER_EMAIL, c).status == BLOCK
    assert evaluate(RETRY_PAYMENT, c).status == ALLOW  # retry is not customer contact


def test_message_limit_and_interval():
    assert evaluate(CUSTOMER_EMAIL, ctx(messages_sent=3)).status == BLOCK
    r = evaluate(CUSTOMER_EMAIL, ctx(messages_sent=1, last_message_hours_ago=5))
    assert r.status == BLOCK and "MIN_MESSAGE_INTERVAL_HOURS" in r.rules
    assert evaluate(CUSTOMER_EMAIL, ctx(messages_sent=1, last_message_hours_ago=30)).status == ALLOW


def test_human_approval_threshold_escalates():
    r = evaluate(PAYMENT_LINK, ctx(amount=100000))
    assert r.status == ESCALATE and "HUMAN_APPROVAL_THRESHOLD" in r.rules
    assert evaluate(PAYMENT_LINK, ctx(amount=99999)).status == ALLOW


def test_overdue_automation_window_escalates_invoices():
    c = ctx(source_type="invoice", failure_class="", days_overdue=31, amount=20000)
    assert evaluate(CUSTOMER_EMAIL, c).status == ESCALATE
    assert evaluate(CUSTOMER_EMAIL, {**c, "days_overdue": 30}).status == ALLOW


def test_already_resolved_blocks_everything_but_no_action():
    c = ctx(already_resolved=True)
    assert evaluate(PAYMENT_LINK, c).status == BLOCK
    assert evaluate(NO_ACTION, c).status == ALLOW


def test_stopping_condition_after_failed_attempts():
    r = evaluate(PAYMENT_LINK, ctx(failed_attempts=2))
    assert r.status == BLOCK and "MAX_FAILED_RECOVERY_ATTEMPTS" in r.rules


def test_human_review_minimum_value_and_routing():
    assert evaluate(HUMAN_REVIEW, ctx(amount=5000)).status == BLOCK
    assert evaluate(HUMAN_REVIEW, ctx(amount=60000)).status == ESCALATE


def test_policy_is_deterministic():
    c = ctx(amount=150000)
    assert evaluate(PAYMENT_LINK, c, Policy()) == evaluate(PAYMENT_LINK, c, Policy())
