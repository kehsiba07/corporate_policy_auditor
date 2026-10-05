from app.services.risk import rank_violations, score_violation


def violation(tid, amount, approver_level, required_level=4, threshold=5000):
    return {
        "policy_id": "P1",
        "transaction_id": tid,
        "amount": amount,
        "threshold": threshold,
        "approver_level": approver_level,
        "required_level": required_level,
        "max_level": None,
    }


def test_score_is_deterministic():
    v = violation("T1", 50000, 1)
    assert score_violation(v) == score_violation(dict(v))


def test_larger_amount_and_bigger_gap_scores_higher():
    small = violation("T1", 5500, 3)
    big = violation("T2", 500000, 1)
    assert score_violation(big) > score_violation(small)


def test_ranking_order_and_ranks():
    ranked = rank_violations(
        [
            violation("LOW", 5100, 3),
            violation("HIGH", 900000, 0),
            violation("MID", 40000, 2),
        ]
    )
    assert [v["transaction_id"] for v in ranked] == ["HIGH", "MID", "LOW"]
    assert [v["rank"] for v in ranked] == [1, 2, 3]


def test_severity_labels_follow_score_bands():
    ranked = rank_violations([violation("HIGH", 5_000_000, 0), violation("LOW", 5001, 3)])
    by_id = {v["transaction_id"]: v for v in ranked}
    assert by_id["HIGH"]["severity"] == "High"
    assert by_id["LOW"]["severity"] in ("Low", "Medium")
    assert by_id["HIGH"]["risk_score"] > by_id["LOW"]["risk_score"]