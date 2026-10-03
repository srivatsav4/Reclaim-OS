import pytest
from app.simulator import (simulate_action, simulate_control, assign_group, unit, SUCCESS, FAILED, ALREADY_RESOLVED, BLOCKED)
from app.service import compute_experiment


def test_simulator_is_deterministic():
    a = [simulate_action(42, "PAYMENT_LINK", 0.5)["result"] for _ in range(5)]
    assert len(set(a)) == 1 and unit(1, "x") == unit(1, "x")


def test_probability_extremes():
    assert simulate_action(7, "RETRY_PAYMENT", 1.0)["result"] == SUCCESS
    assert simulate_action(7, "RETRY_PAYMENT", 0.0)["result"] in (FAILED, "CUSTOMER_DECLINED")


def test_already_resolved_and_blocked_outcomes():
    assert simulate_action(1, "RETRY_PAYMENT", 0.9, already_resolved=True)["result"] == ALREADY_RESOLVED
    assert simulate_action(1, "RETRY_PAYMENT", 0.9, allowed=False)["result"] == BLOCKED


def test_forced_outcomes_single_and_per_attempt():
    assert simulate_action(1, "RETRY_PAYMENT", 0.0, forced="SUCCESS")["result"] == SUCCESS
    assert simulate_action(1, "RETRY_PAYMENT", 1.0, forced=["FAILED", "FAILED"], attempt=1)["result"] == FAILED


def test_group_assignment_deterministic_and_near_split():
    g = [assign_group(i, 42, 0.7) for i in range(2000)]
    assert g == [assign_group(i, 42, 0.7) for i in range(2000)]
    assert 0.65 < g.count("AI") / 2000 < 0.75
    assert [assign_group(i, 1, 0.7) for i in range(50)] != [assign_group(i, 2, 0.7) for i in range(50)]


def test_control_group_organic_recovery_rate_tracks_probability():
    hits = sum(simulate_control(i, 0.2) for i in range(4000))
    assert 0.17 < hits / 4000 < 0.23


def test_experiment_incremental_math():
    ai = [{"amount": 1000, "recovered": 1000}] * 6 + [{"amount": 1000, "recovered": 0}] * 4
    ctl = [{"amount": 1000, "recovered": 1000}] * 1 + [{"amount": 1000, "recovered": 0}] * 9
    r = compute_experiment(ai, ctl)
    assert r["observed_recovery"] == 6000
    assert r["ai"]["rate_value"] == pytest.approx(0.6) and r["control"]["rate_value"] == pytest.approx(0.1)
    assert r["incremental_recovery"] == pytest.approx(5000)
    assert r["lift_pp"] == pytest.approx(50) and r["ci95_pp"][0] < 50 < r["ci95_pp"][1]
    assert "not proof of causality" in r["note"]


def test_experiment_handles_empty_control():
    r = compute_experiment([{"amount": 100, "recovered": 100}], [])
    assert r["control"]["rate_value"] == 0 and r["incremental_recovery"] == pytest.approx(100)
