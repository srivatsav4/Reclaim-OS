"""Deterministic Policy Gate. AI recommends; this module decides ALLOW / BLOCK / ESCALATE."""
from dataclasses import dataclass, asdict, field

ALLOW, BLOCK, ESCALATE = "ALLOW", "BLOCK", "ESCALATE"

RETRY_PAYMENT = "RETRY_PAYMENT"
PAYMENT_LINK = "PAYMENT_LINK"
CHECKOUT_RECOVERY = "CHECKOUT_RECOVERY"
CUSTOMER_EMAIL = "CUSTOMER_EMAIL"
CUSTOMER_NOTIFICATION = "CUSTOMER_NOTIFICATION"
INVOICE_REMINDER = "INVOICE_REMINDER"
PROMISE_TO_PAY_FOLLOWUP = "PROMISE_TO_PAY_FOLLOWUP"
HUMAN_REVIEW = "HUMAN_REVIEW"
NO_ACTION = "NO_ACTION"

CONTACT_ACTIONS = {PAYMENT_LINK, CHECKOUT_RECOVERY, CUSTOMER_EMAIL, CUSTOMER_NOTIFICATION,
                   INVOICE_REMINDER, PROMISE_TO_PAY_FOLLOWUP}
NON_RETRYABLE_CLASSES = {"HARD", "FRAUD", "AUTH"}


@dataclass
class Policy:
    MAX_PAYMENT_RETRIES: int = 2
    MAX_CUSTOMER_MESSAGES: int = 3
    MIN_MESSAGE_INTERVAL_HOURS: int = 24
    HIGH_VALUE_THRESHOLD: float = 100000
    HUMAN_APPROVAL_THRESHOLD: float = 100000
    MAX_OVERDUE_AUTOMATION_DAYS: int = 30
    MAX_FAILED_RECOVERY_ATTEMPTS: int = 2
    MIN_HUMAN_REVIEW_VALUE: float = 25000
    MIN_NET_GAIN: float = 100
    DAILY_RECOVERY_BUDGET: float = 10000

    def as_dict(self):
        return asdict(self)


POLICY_DESCRIPTIONS = {
    "MAX_PAYMENT_RETRIES": "Maximum automated payment retries per payment",
    "MAX_CUSTOMER_MESSAGES": "Maximum recovery messages sent to a customer per case",
    "MIN_MESSAGE_INTERVAL_HOURS": "Minimum hours between customer messages",
    "HIGH_VALUE_THRESHOLD": "Amount (INR) treated as high value",
    "HUMAN_APPROVAL_THRESHOLD": "Amount (INR) at or above which a human must approve automated action",
    "MAX_OVERDUE_AUTOMATION_DAYS": "Invoices overdue longer than this leave automation and need a human",
    "MAX_FAILED_RECOVERY_ATTEMPTS": "Stop automation after this many failed recovery attempts",
    "MIN_HUMAN_REVIEW_VALUE": "Smallest amount (INR) worth routing to a human reviewer",
    "MIN_NET_GAIN": "Minimum expected net gain (INR) over doing nothing to justify acting",
    "DAILY_RECOVERY_BUDGET": "Daily intervention budget (INR)",
}


@dataclass
class PolicyResult:
    status: str
    reasons: list = field(default_factory=list)
    rules: list = field(default_factory=list)


def evaluate(action: str, ctx: dict, policy: Policy | None = None) -> PolicyResult:
    """Pure, deterministic evaluation of one candidate action against policy."""
    p = policy or Policy()
    if action == NO_ACTION:
        return PolicyResult(ALLOW, ["Doing nothing is always permitted"], [])

    noun = {"payment": "payment", "subscription": "subscription payment",
            "checkout": "checkout", "invoice": "invoice"}.get(ctx.get("source_type"), "payment")
    if ctx.get("already_resolved"):
        return PolicyResult(BLOCK, [f"Customer already resolved the {noun}"], ["ALREADY_RESOLVED"])
    if ctx.get("failed_attempts", 0) >= p.MAX_FAILED_RECOVERY_ATTEMPTS:
        return PolicyResult(BLOCK, [f"Stopping condition reached: {ctx['failed_attempts']} failed recovery attempts "
                                    f"(limit {p.MAX_FAILED_RECOVERY_ATTEMPTS})"], ["MAX_FAILED_RECOVERY_ATTEMPTS"])

    reasons, rules = [], []
    if action == RETRY_PAYMENT:
        if ctx.get("retries_done", 0) >= p.MAX_PAYMENT_RETRIES:
            return PolicyResult(BLOCK, [f"Retry limit exceeded ({ctx['retries_done']}/{p.MAX_PAYMENT_RETRIES} retries used)"],
                                ["MAX_PAYMENT_RETRIES"])
        if ctx.get("failure_class") in NON_RETRYABLE_CLASSES:
            return PolicyResult(BLOCK, ["Failure type is not retryable without customer action"], ["NON_RETRYABLE_FAILURE"])

    if action in CONTACT_ACTIONS:
        if not ctx.get("contact_allowed", True):
            return PolicyResult(BLOCK, ["Customer has not permitted contact"], ["CONTACT_PERMISSION"])
        if ctx.get("messages_sent", 0) >= p.MAX_CUSTOMER_MESSAGES:
            return PolicyResult(BLOCK, [f"Communication limit reached ({ctx['messages_sent']}/{p.MAX_CUSTOMER_MESSAGES} messages)"],
                                ["MAX_CUSTOMER_MESSAGES"])
        last = ctx.get("last_message_hours_ago")
        if last is not None and last < p.MIN_MESSAGE_INTERVAL_HOURS:
            return PolicyResult(BLOCK, [f"Last message sent {last}h ago; minimum interval is {p.MIN_MESSAGE_INTERVAL_HOURS}h"],
                                ["MIN_MESSAGE_INTERVAL_HOURS"])

    amount = ctx.get("amount", 0)
    if action == HUMAN_REVIEW:
        if amount < p.MIN_HUMAN_REVIEW_VALUE and ctx.get("days_overdue", 0) <= p.MAX_OVERDUE_AUTOMATION_DAYS:
            return PolicyResult(BLOCK, [f"Amount is below the human-review minimum (₹{p.MIN_HUMAN_REVIEW_VALUE:,.0f})"],
                                ["MIN_HUMAN_REVIEW_VALUE"])
        return PolicyResult(ESCALATE, ["Routed to the human review queue"], ["HUMAN_REVIEW_QUEUE"])

    if amount >= p.HUMAN_APPROVAL_THRESHOLD:
        reasons.append(f"Amount ₹{amount:,.0f} is at or above the human approval threshold (₹{p.HUMAN_APPROVAL_THRESHOLD:,.0f})")
        rules.append("HUMAN_APPROVAL_THRESHOLD")
    if ctx.get("source_type") == "invoice" and ctx.get("days_overdue", 0) > p.MAX_OVERDUE_AUTOMATION_DAYS:
        reasons.append(f"Invoice is {ctx['days_overdue']} days overdue (automation limit {p.MAX_OVERDUE_AUTOMATION_DAYS})")
        rules.append("MAX_OVERDUE_AUTOMATION_DAYS")
    if ctx.get("failure_class") == "FRAUD":
        reasons.append("Payment carries a suspected-fraud flag and needs a risk review")
        rules.append("FRAUD_REVIEW")
    if rules:
        return PolicyResult(ESCALATE, reasons, rules)
    return PolicyResult(ALLOW, ["Within all policy limits; no human approval required"], [])
