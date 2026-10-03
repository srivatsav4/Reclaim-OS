"""RECLAIM OS API. Run: uvicorn app.main:app --app-dir backend"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import service as svc
from .db import AI_MODE, ROOT, SessionLocal, get_db, init_db
from .models import (AuditEvent, Customer, HumanReview, RecoveryAction, RecoveryCase, Experiment)
from .policy import POLICY_DESCRIPTIONS
from .seed import SCENARIOS, reset_demo, seed
from .service import AppError

log = logging.getLogger("reclaim")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(Customer)):
            log.info("Seeding demo database...")
            seed(db)
    yield


app = FastAPI(title="RECLAIM OS API", version="1.0.0", lifespan=lifespan,
              description="AI Revenue Recovery Operating System. All data is DEMO / SIMULATED.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(AppError)
async def app_error(_: Request, e: AppError):
    return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}" for err in e.errors())
    return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": msg}}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, e: Exception):
    log.exception("Unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong on our side."}}, status_code=500)


class ReviewBody(BaseModel):
    by: str = Field("demo_reviewer", min_length=1, max_length=40)
    note: Optional[str] = Field(None, max_length=500)


class ExperimentBody(BaseModel):
    split: float = Field(0.7, ge=0.1, le=0.9)
    seed: int = Field(42, ge=0, le=1_000_000)
    name: Optional[str] = Field(None, max_length=120)


class LabBody(BaseModel):
    budget: float = Field(10000, ge=0, le=100_000_000)
    segment: str = Field("ALL", pattern="^(ALL|Consumer|SMB|Mid-Market|Enterprise)$")
    strategy: str = "OPTIMIZER"
    retry_delay_hours: int = Field(48, ge=0, le=168)
    contact_frequency: int = Field(2, ge=1, le=7)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "ai_mode": AI_MODE, "data": "DEMO / SIMULATED"}


@app.get("/api/dashboard", tags=["dashboard"])
def get_dashboard(db: Session = Depends(get_db)):
    return svc.dashboard(db)


@app.get("/api/policies", tags=["policy"])
def get_policies(db: Session = Depends(get_db)):
    p = svc.load_policy(db).as_dict()
    return [{"key": k, "value": v, "description": POLICY_DESCRIPTIONS[k]} for k, v in p.items()]


@app.get("/api/scenarios", tags=["demo"])
def get_scenarios(db: Session = Depends(get_db)):
    out = []
    for s in SCENARIOS:
        c = db.scalar(select(RecoveryCase).where(RecoveryCase.scenario == s["key"]))
        if c:
            cu = db.get(Customer, c.customer_id)
            out.append({**s, "case_id": c.id, "customer": cu.name, "customer_id": cu.id, "amount": c.revenue_at_risk,
                        "status": c.status, "decision": c.decision})
    return out


@app.get("/api/customers", tags=["customers"])
def list_customers(q: Optional[str] = None, segment: Optional[str] = None, at_risk_only: bool = False,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    stmt = select(Customer)
    if q:
        stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q}%")))
    if segment:
        stmt = stmt.where(Customer.segment == segment)
    if at_risk_only:
        stmt = stmt.where(Customer.id.in_(select(RecoveryCase.customer_id)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Customer.id).limit(limit).offset(offset)).all()
    exposure = {r[0]: r[1] for r in db.execute(select(RecoveryCase.customer_id, func.sum(RecoveryCase.revenue_at_risk))
                                              .where(RecoveryCase.customer_id.in_([c.id for c in rows]),
                                                     RecoveryCase.status.notin_(["RECOVERED", "CLOSED_RESOLVED", "CONTROL_RECOVERED"]))
                                              .group_by(RecoveryCase.customer_id))}
    return {"total": total, "items": [{"id": c.id, "name": c.name, "email": c.email, "segment": c.segment,
                                       "lifetime_value": c.lifetime_value, "risk_level": c.risk_level,
                                       "contact_allowed": c.contact_allowed, "exposure": exposure.get(c.id, 0.0)} for c in rows]}


@app.get("/api/customers/{customer_id}", tags=["customers"])
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return svc.customer_graph(db, customer_id)


@app.get("/api/recovery-cases", tags=["cases"])
def list_cases(status: Optional[str] = None, source_type: Optional[str] = None, decision: Optional[str] = None,
               group: Optional[str] = None, customer_id: Optional[int] = None, scenario_only: bool = False,
               sort: str = Query("amount", pattern="^(amount|score|recent)$"),
               limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    stmt = select(RecoveryCase)
    if status:
        stmt = stmt.where(RecoveryCase.status.in_(status.split(",")))
    for col, v in ((RecoveryCase.source_type, source_type), (RecoveryCase.decision, decision),
                   (RecoveryCase.group, group), (RecoveryCase.customer_id, customer_id)):
        if v is not None:
            stmt = stmt.where(col == v)
    if scenario_only:
        stmt = stmt.where(RecoveryCase.scenario.is_not(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"amount": RecoveryCase.revenue_at_risk.desc(), "score": RecoveryCase.recoverability_score.desc(),
             "recent": RecoveryCase.created_at.desc()}[sort]
    rows = db.scalars(stmt.order_by(order).limit(limit).offset(offset)).all()
    cust = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_({r.customer_id for r in rows})))}
    return {"total": total, "items": [svc.case_dict(c, cust.get(c.customer_id)) for c in rows]}


@app.get("/api/recovery-cases/{case_id}", tags=["cases"])
def get_case(case_id: int, db: Session = Depends(get_db)):
    c = svc.get_case(db, case_id)
    d = svc.case_dict(c, db.get(Customer, c.customer_id), full=True)
    d["actions"] = [svc.action_dict(a) for a in db.scalars(select(RecoveryAction).where(RecoveryAction.recovery_case_id == c.id).order_by(RecoveryAction.id))]
    d["audit"] = [svc.audit_dict(e) for e in db.scalars(select(AuditEvent).where(AuditEvent.case_id == c.id).order_by(AuditEvent.timestamp, AuditEvent.id))]
    r = db.scalar(select(HumanReview).where(HumanReview.recovery_case_id == c.id).order_by(HumanReview.id.desc()))
    d["review"] = svc.review_dict(db, r) if r else None
    return d


@app.post("/api/recovery-cases/{case_id}/analyze", tags=["cases"])
def analyze(case_id: int, db: Session = Depends(get_db)):
    c = svc.get_case(db, case_id)
    if c.status in svc.TERMINAL:
        raise AppError("CASE_CLOSED", f"Case is already {c.status}", 409)
    svc.analyze_case(db, c)
    db.commit()
    return get_case(case_id, db)


@app.post("/api/recovery-cases/{case_id}/execute", tags=["cases"])
def execute(case_id: int, db: Session = Depends(get_db)):
    res = svc.execute_case(db, case_id)
    db.commit()
    return res


@app.post("/api/recovery-cases/{case_id}/approve", tags=["human review"])
def approve(case_id: int, body: ReviewBody = ReviewBody(), db: Session = Depends(get_db)):
    res = svc.approve_case(db, case_id, by=body.by, note=body.note)
    db.commit()
    return res


@app.post("/api/recovery-cases/{case_id}/reject", tags=["human review"])
def reject(case_id: int, body: ReviewBody = ReviewBody(), db: Session = Depends(get_db)):
    res = svc.reject_case(db, case_id, by=body.by, note=body.note)
    db.commit()
    return res


@app.post("/api/recovery-cases/{case_id}/request-info", tags=["human review"])
def request_info(case_id: int, body: ReviewBody = ReviewBody(), db: Session = Depends(get_db)):
    res = svc.request_info(db, case_id, by=body.by, note=body.note)
    db.commit()
    return res


@app.get("/api/reviews", tags=["human review"])
def list_reviews(status: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(HumanReview).order_by(HumanReview.created_at.desc())
    if status == "OPEN":
        stmt = stmt.where(HumanReview.status.in_(["PENDING", "INFO_REQUESTED"]))
    elif status:
        stmt = stmt.where(HumanReview.status == status)
    return {"items": [svc.review_dict(db, r) for r in db.scalars(stmt)]}


@app.get("/api/recovery-actions", tags=["actions"])
def list_actions(case_id: Optional[int] = None, executed_only: bool = False, limit: int = Query(100, ge=1, le=500),
                 db: Session = Depends(get_db)):
    stmt = select(RecoveryAction).order_by(RecoveryAction.id.desc())
    if case_id:
        stmt = stmt.where(RecoveryAction.recovery_case_id == case_id)
    if executed_only:
        stmt = stmt.where(RecoveryAction.execution_status.notin_(["PLANNED", "NOT_SELECTED"]))
    return {"items": [svc.action_dict(a) for a in db.scalars(stmt.limit(limit))]}


@app.get("/api/audit", tags=["audit"])
def get_audit(customer_id: Optional[int] = None, case_id: Optional[int] = None, event_type: Optional[str] = None,
              actor: Optional[str] = None, policy: Optional[str] = None, outcome: Optional[str] = None,
              date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, order: str = Query("desc", pattern="^(asc|desc)$"),
              limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    stmt = select(AuditEvent)
    for col, v in ((AuditEvent.customer_id, customer_id), (AuditEvent.case_id, case_id), (AuditEvent.event_type, event_type),
                   (AuditEvent.actor, actor), (AuditEvent.outcome, outcome)):
        if v is not None:
            stmt = stmt.where(col == v)
    if policy:
        stmt = stmt.where(AuditEvent.policy.ilike(f"%{policy}%"))
    if date_from:
        stmt = stmt.where(AuditEvent.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(AuditEvent.timestamp <= date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    o = AuditEvent.timestamp.desc() if order == "desc" else AuditEvent.timestamp.asc()
    rows = db.scalars(stmt.order_by(o, AuditEvent.id.desc() if order == "desc" else AuditEvent.id).limit(limit)).all()
    return {"total": total, "items": [svc.audit_dict(e) for e in rows]}


@app.get("/api/experiments", tags=["experiments"])
def list_experiments(db: Session = Depends(get_db)):
    return {"label": "SIMULATED", "items": [svc.experiment_dict(e) for e in db.scalars(select(Experiment).order_by(Experiment.id.desc()))]}


@app.post("/api/experiments/run", tags=["experiments"])
def run_experiment(body: ExperimentBody = ExperimentBody(), db: Session = Depends(get_db)):
    e = svc.run_experiment(db, split=body.split, seed=body.seed, name=body.name)
    db.commit()
    return svc.experiment_dict(e)


@app.get("/api/recovery-lab/{case_id}", tags=["recovery lab"])
def lab_case(case_id: int, db: Session = Depends(get_db)):
    out = svc.lab_case(db, case_id)
    db.commit()
    return out


@app.post("/api/recovery-lab/simulate", tags=["recovery lab"])
def lab_simulate(body: LabBody, db: Session = Depends(get_db)):
    return svc.lab_simulate(db, budget=body.budget, segment=body.segment, strategy=body.strategy,
                            retry_delay_hours=body.retry_delay_hours, contact_frequency=body.contact_frequency)


@app.post("/api/simulator/reset", tags=["system"])
def simulator_reset(db: Session = Depends(get_db)):
    return {"status": "reset", **reset_demo(db)}


# ---- optionally serve the built frontend (used by Docker / single-process demo)
_dist = Path(os.getenv("STATIC_DIR", ROOT / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Unknown API route"}}, status_code=404)
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
