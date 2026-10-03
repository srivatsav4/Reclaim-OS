"""Deterministic recovery simulator. No randomness: outcomes are a pure function of (case, action, attempt)."""
import hashlib

SUCCESS, FAILED, ALREADY_RESOLVED, BLOCKED, CUSTOMER_DECLINED = (
    "SUCCESS", "FAILED", "ALREADY_RESOLVED", "BLOCKED", "CUSTOMER_DECLINED")
CONTACT_LIKE = {"PAYMENT_LINK", "CHECKOUT_RECOVERY", "CUSTOMER_EMAIL", "CUSTOMER_NOTIFICATION",
                "INVOICE_REMINDER", "PROMISE_TO_PAY_FOLLOWUP", "HUMAN_REVIEW"}


def unit(case_id: int, salt: str) -> float:
    """Deterministic pseudo-uniform value in [0, 1)."""
    h = hashlib.sha256(f"{case_id}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0x100000000


def assign_group(case_id: int, seed: int = 42, split: float = 0.7) -> str:
    return "AI" if unit(case_id, f"group:{seed}") < split else "CONTROL"


def simulate_action(case_id: int, action: str, probability: float, *, already_resolved=False,
                    allowed=True, forced: str | None = None, attempt: int = 0) -> dict:
    if already_resolved:
        return {"result": ALREADY_RESOLVED, "note": "Customer had already resolved this before the action ran"}
    if not allowed:
        return {"result": BLOCKED, "note": "Policy gate blocked execution"}
    if forced:  # showcase scenarios: a fixed outcome, or a per-attempt list like ["FAILED", "FAILED"]
        f = forced[attempt] if isinstance(forced, list) and attempt < len(forced) else (forced if isinstance(forced, str) and attempt == 0 else None)
        if f:
            return {"result": f, "note": "Deterministic showcase scenario"}
    u = unit(case_id, f"{action}:{attempt}")
    if u < probability:
        return {"result": SUCCESS, "note": "Simulated recovery succeeded"}
    if action in CONTACT_LIKE and u > 0.93:
        return {"result": CUSTOMER_DECLINED, "note": "Simulated customer declined to pay"}
    return {"result": FAILED, "note": "Simulated recovery attempt failed"}


def simulate_control(case_id: int, organic_probability: float) -> bool:
    """Control group receives no automated action; some customers still pay on their own."""
    return unit(case_id, "control") < organic_probability
