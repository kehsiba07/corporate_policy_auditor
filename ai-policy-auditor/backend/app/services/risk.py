import math

SEVERITY_BANDS = ((70.0, "High"), (40.0, "Medium"), (0.0, "Low"))


def _severity(score: float) -> str:
    for floor, label in SEVERITY_BANDS:
        if score >= floor:
            return label
    return "Low"


def score_violation(v: dict) -> float:
    """
    Deterministic 0-100 score:
      financial impact   (0-50): log-scaled transaction amount
      authority gap      (0-30): how many hierarchy levels the approver falls short
      threshold excess   (0-20): how far the amount exceeds the policy threshold
    """
    amount = max(float(v.get("amount") or 0), 0.0)
    financial = min(50.0, 10.0 * math.log10(1.0 + amount))

    approver_level = v.get("approver_level", -1)
    gap = 0
    if v.get("required_level") is not None:
        gap = max(gap, v["required_level"] - approver_level)
    if v.get("max_level") is not None:
        gap = max(gap, approver_level - v["max_level"])
    authority = min(30.0, 10.0 * gap)

    threshold = v.get("threshold")
    excess = 0.0
    if threshold and threshold > 0:
        excess = min(20.0, 20.0 * max(0.0, amount - threshold) / threshold)

    return round(min(100.0, financial + authority + excess), 1)


def rank_violations(violations: list) -> list:
    """Returns new dicts with risk_score, severity and rank (1 = most severe)."""
    scored = []
    for v in violations:
        item = dict(v)
        item["risk_score"] = score_violation(item)
        item["severity"] = _severity(item["risk_score"])
        scored.append(item)

    scored.sort(
        key=lambda x: (
            -x["risk_score"],
            -float(x.get("amount") or 0),
            str(x.get("policy_id")),
            str(x.get("transaction_id")),
        )
    )
    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank
    return scored