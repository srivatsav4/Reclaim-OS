from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), index=True)
    segment: Mapped[str] = mapped_column(String(30), index=True)
    lifetime_value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    preferred_channel: Mapped[str] = mapped_column(String(20))
    contact_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_level: Mapped[str] = mapped_column(String(10), default="LOW")
    successful_payments: Mapped[int] = mapped_column(Integer, default=0)
    previous_recoveries: Mapped[int] = mapped_column(Integer, default=0)
    engagement: Mapped[float] = mapped_column(Float, default=0.5)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), index=True)  # SUCCEEDED/FAILED/RESOLVED/RECOVERED
    failure_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Checkout(Base):
    __tablename__ = "checkouts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    cart_value: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), index=True)  # COMPLETED/ABANDONED/RECOVERED/RESOLVED
    started_at: Mapped[datetime] = mapped_column(DateTime)
    abandoned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    device: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(20))


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    billing_cycle: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), index=True)  # ACTIVE/PAST_DUE
    next_billing_date: Mapped[datetime] = mapped_column(DateTime)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    due_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), index=True)  # PAID/OVERDUE/RESOLVED
    days_overdue: Mapped[int] = mapped_column(Integer, default=0)
    promise_to_pay_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), index=True)  # payment/checkout/subscription/invoice
    source_id: Mapped[int] = mapped_column(Integer)
    revenue_at_risk: Mapped[float] = mapped_column(Float)
    recoverability_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="LOW")
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    root_cause: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    expected_recovery: Mapped[float] = mapped_column(Float, default=0.0)
    actual_recovery: Mapped[float] = mapped_column(Float, default=0.0)
    decision: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)  # ACT/ESCALATE/NO_ACTION
    group: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # AI/CONTROL
    scenario: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    experiment_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    organic_recovery: Mapped[float] = mapped_column(Float, default=0.0)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    estimated_cost: Mapped[float] = mapped_column(Float)
    expected_probability: Mapped[float] = mapped_column(Float)
    expected_recovery: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float, default=0.0)
    friction: Mapped[str] = mapped_column(String(10), default="low")
    policy_status: Mapped[str] = mapped_column(String(10))  # ALLOW/BLOCK/ESCALATE
    policy_reasons: Mapped[list] = mapped_column(JSON, default=list)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recovery_action_id: Mapped[int] = mapped_column(ForeignKey("recovery_actions.id"), index=True)
    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), index=True)
    result: Mapped[str] = mapped_column(String(24))
    amount_recovered: Mapped[float] = mapped_column(Float, default=0.0)
    incremental_recovery: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecoveryPolicy(Base):
    __tablename__ = "recovery_policies"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(200), default="")


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), index=True)
    decision: Mapped[str] = mapped_column(String(12))
    selected_action: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reasoning: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(12), default="demo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    split: Mapped[float] = mapped_column(Float)
    seed: Mapped[int] = mapped_column(Integer)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    label: Mapped[str] = mapped_column(String(40), default="SIMULATED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column(Integer)
    case_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    policy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class HumanReview(Base):
    __tablename__ = "human_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    policy_conflict: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    recommended_step: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
