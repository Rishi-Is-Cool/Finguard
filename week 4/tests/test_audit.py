import json

import pytest

from backend.audit import AuditLog


@pytest.fixture
def log(tmp_path):
    return AuditLog(tmp_path)


def test_chain_verifies(log):
    for i in range(3):
        log.append("abcd1234", "step", {"i": i})
    v = log.verify("abcd1234")
    assert v["valid"] and v["events"] == 3 and len(v["head"]) == 64


def test_editing_a_past_event_breaks_the_chain(log, tmp_path):
    for i in range(3):
        log.append("abcd1234", "step", {"i": i})
    path = tmp_path / "abcd1234.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["payload"]["i"] = 99
    lines[1] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert log.verify("abcd1234") == {"valid": False, "events": 3, "broken_at": 2, "head": None}


def test_deleting_an_event_breaks_the_chain(log, tmp_path):
    for i in range(3):
        log.append("abcd1234", "step", {"i": i})
    path = tmp_path / "abcd1234.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert log.verify("abcd1234")["broken_at"] == 2


def test_reviews_keep_latest_decision(log):
    log.append("abcd1234", "human_review", {"txn_id": "T0001", "decision": "needs_escalation", "note": ""}, actor="a")
    log.append("abcd1234", "human_review", {"txn_id": "T0001", "decision": "false_positive", "note": "EMI"}, actor="b")
    r = log.reviews("abcd1234")["T0001"]
    assert r["decision"] == "false_positive" and r["reviewer"] == "b" and r["note"] == "EMI"


@pytest.mark.parametrize("bad", ["../etc/passwd", "ABCD1234", "abcd123", "abcd12345", ""])
def test_rejects_unsafe_document_ids(log, bad):
    with pytest.raises(ValueError):
        log.append(bad, "step", {})
