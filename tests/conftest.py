import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"  # isolated in-memory DB for tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/simulator/reset")
        yield c


def ctx(**kw):
    base = dict(source_type="payment", amount=20000, failure_reason="insufficient_funds", failure_class="TEMPORARY",
                retries_done=0, failed_attempts=0, messages_sent=0, last_message_hours_ago=None, hours_since_failure=10,
                ltv=80000, segment="SMB", contact_allowed=True, successful_payments=5, previous_recoveries=0,
                engagement=0.6, already_resolved=False, days_overdue=0, payment_method="card")
    base.update(kw)
    return base
