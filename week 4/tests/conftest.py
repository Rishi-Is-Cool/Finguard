import os
import tempfile

# Before any backend import: no model warm-up, audit logs in a throwaway dir,
# and no Jev key leaking in from a developer's .env.
os.environ["FINGUARD_SKIP_WARMUP"] = "1"
os.environ["FINGUARD_AUDIT_DIR"] = tempfile.mkdtemp(prefix="finguard-test-audit-")
os.environ["TYPESAFE_API_KEY"] = ""

import pytest


def txn(**overrides):
    base = {"date": "2024-03-01", "time": "14:00", "account": "ACC001", "beneficiary": "Priya Ltd",
            "description": "Invoice payment", "amount": "12000", "type": "debit"}
    return {**base, **overrides}


@pytest.fixture
def make_txn():
    return txn
