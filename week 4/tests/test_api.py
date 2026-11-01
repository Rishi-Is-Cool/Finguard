"""HTTP surface that needs no model or API key: upload, validation, the /api
mirror, the audit trail, human review and the case-file export."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.pipeline import flagged_transactions, normalize_transactions, run_rules


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def test_health_reports_effective_models(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["version"] == main.VERSION
    assert h["classifier_mode"] == "llm_only" and h["screener"] is None


def test_api_prefix_mirrors_routes(client):
    assert client.get("/api/health").json() == client.get("/health").json()


def test_sample_upload(client):
    r = client.post("/api/upload/sample").json()
    assert r["row_count"] == 200 and len(r["document_id"]) == 8
    events = client.get(f"/audit/{r['document_id']}").json()["events"]
    assert events[0]["type"] == "input_received" and len(events[0]["payload"]["sha256"]) == 64


def test_rejects_bad_csv(client):
    bad = io.BytesIO(b"date,amount\n2024-01-01,5\n")
    r = client.post("/upload", files={"file": ("x.csv", bad, "text/csv")})
    assert r.status_code == 400 and "Missing columns" in r.json()["detail"]


def test_rejects_non_csv(client):
    r = client.post("/upload", files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400


def test_rejects_oversized_upload(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD", 10)
    r = client.post("/upload", files={"file": ("x.csv", io.BytesIO(b"x" * 100), "text/csv")})
    assert r.status_code == 413


@pytest.mark.parametrize("doc_id", ["..%2F..%2Fsecrets", "ZZZZZZZZ", "abc"])
def test_unsafe_ids_are_404(client, doc_id):
    assert client.get(f"/audit/{doc_id}").status_code == 404
    assert client.get(f"/report/{doc_id}").status_code == 404


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT", 2)
    main._hits.clear()

    class Req:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = None
    main._check_rate_limit(Req())
    main._check_rate_limit(Req())
    with pytest.raises(main.HTTPException) as e:
        main._check_rate_limit(Req())
    assert e.value.status_code == 429 and "Retry-After" in e.value.headers


def test_spoofed_forwarded_for_does_not_reset_limit():
    class Req:
        def __init__(self, spoof):
            self.headers = {"x-forwarded-for": f"{spoof}, 198.51.100.7"}
        client = None
    assert main._client_ip(Req("1.1.1.1")) == main._client_ip(Req("2.2.2.2")) == "198.51.100.7"


@pytest.fixture
def analysed_doc(client, make_txn):
    """An upload whose rules step has been recorded, as /analyze would do."""
    doc_id = client.post("/upload/sample").json()["document_id"]
    txns = normalize_transactions([make_txn(time="02:00", amount="49800"), make_txn()])
    cands = flagged_transactions(run_rules(txns)["flags"])
    main.audit_log.append(doc_id, "rules_applied", {
        "ruleset_version": "test", "flags": [
            {"flag_id": "F0001", "rule": "structuring", "severity": "HIGH", "scope": "transaction",
             "txn_id": "T0001", "account": "ACC001", "reason": "r"}],
        "flagged_transactions": [{k: c["transaction"][k] for k in
                                  ("txn_id", "date", "time", "account", "beneficiary", "description", "amount", "type")}
                                 for c in cands]})
    return doc_id


def test_review_is_chained_and_exported(client, analysed_doc):
    r = client.post(f"/api/review/{analysed_doc}", json={
        "txn_id": "T0001", "decision": "false_positive", "note": "Known EMI", "reviewer": "Asha"})
    assert r.status_code == 200
    body = r.json()
    assert body["chain"]["valid"] and body["reviews"]["T0001"]["reviewer"] == "Asha"

    rows = list(csv.DictReader(io.StringIO(client.get(f"/audit/{analysed_doc}/export.csv").text)))
    assert len(rows) == 1 and rows[0]["txn_id"] == "T0001"
    assert rows[0]["human_decision"] == "false_positive" and rows[0]["review_note"] == "Known EMI"
    assert rows[0]["route"] == "not_screened" and rows[0]["audit_chain_head"] == body["chain"]["head"]


def test_review_validation(client, analysed_doc):
    assert client.post(f"/review/{analysed_doc}", json={"txn_id": "T9999", "decision": "false_positive"}).status_code == 404
    assert client.post(f"/review/{analysed_doc}", json={"txn_id": "T0001", "decision": "delete_it"}).status_code == 422
    assert client.post(f"/review/{analysed_doc}", json={"txn_id": "../x", "decision": "false_positive"}).status_code == 422
