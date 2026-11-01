import pytest

from backend.pipeline import flagged_transactions, normalize_transactions, run_rules


def test_normalize_assigns_ids_and_types(make_txn):
    out = normalize_transactions([make_txn(), make_txn(amount="49800.50", type="DEBIT")])
    assert [t["txn_id"] for t in out] == ["T0001", "T0002"]
    assert out[1]["amount"] == 49800.5 and out[1]["type"] == "debit"
    assert out[0]["weekday"] == "Friday" and out[0]["hour"] == 14


def test_normalize_rejects_missing_columns(make_txn):
    row = make_txn()
    del row["beneficiary"]
    with pytest.raises(ValueError, match="beneficiary"):
        normalize_transactions([row])


def test_normalize_rejects_bad_values(make_txn):
    with pytest.raises(ValueError, match="Row 2"):
        normalize_transactions([make_txn(), make_txn(amount="lots")])


def test_structuring_only_on_debits(make_txn):
    txns = normalize_transactions([make_txn(amount="49800"), make_txn(amount="49800", type="credit")])
    flags = [f for f in run_rules(txns)["flags"] if f["flag_type"] == "structuring"]
    assert len(flags) == 1 and flags[0]["severity"] == "HIGH" and flags[0]["transaction"]["txn_id"] == "T0001"


def test_velocity_is_account_level(make_txn):
    txns = normalize_transactions([make_txn() for _ in range(21)] + [make_txn(account="ACC002")])
    vel = [f for f in run_rules(txns)["flags"] if f["flag_type"] == "velocity"]
    assert len(vel) == 1
    assert vel[0]["scope"] == "account" and vel[0]["transaction"] == {"account": "ACC001"}
    assert vel[0]["evidence"]["transaction_count"] == 21


def test_clean_transaction_is_not_flagged(make_txn):
    run = run_rules(normalize_transactions([make_txn()]))
    assert run["flags"] == [] and run["score"]["label"] == "LOW"


def test_flagged_transactions_dedup_and_order(make_txn):
    txns = normalize_transactions([
        make_txn(time="22:30", amount="1000"),                               # MEDIUM late night
        make_txn(time="02:00", amount="49800", beneficiary="FastCash"),     # three HIGH rules
        make_txn(time="02:00", amount="30000"),                              # one HIGH rule
    ])
    cands = flagged_transactions(run_rules(txns)["flags"])
    assert [c["transaction"]["txn_id"] for c in cands] == ["T0002", "T0003", "T0001"]
    assert cands[0]["rule_severity"] == "HIGH" and len(cands[0]["rules"]) == 3
    assert cands[2]["rule_severity"] == "MEDIUM"
