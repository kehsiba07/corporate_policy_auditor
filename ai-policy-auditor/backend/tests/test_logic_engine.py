from app.services.logic_engine import role_level, verify_compliance_fol


def policy(pid="P1", threshold=5000, op=">", min_role="manager", max_role=None):
    return {
        "id": pid,
        "description": "test policy",
        "threshold": threshold,
        "operator": op,
        "min_approver_role": min_role,
        "max_approver_role": max_role,
        "source_quote": "test quote",
        "page": 1,
    }


def txn(tid, amount, approver):
    return {
        "id": tid,
        "amount": amount,
        "employee_role": "staff",
        "approved_by_role": approver,
        "source_quote": "test quote",
        "page": 1,
    }


def test_known_violation_is_detected():
    result = verify_compliance_fol(
        {"policies": [policy()], "transactions": [txn("T1", 6000, "staff")]}
    )
    assert len(result["violations"]) == 1
    v = result["violations"][0]
    assert v["policy_id"] == "P1"
    assert v["transaction_id"] == "T1"
    assert any("P1" in label for label in v["unsat_core"])


def test_compliant_case_has_no_violations():
    result = verify_compliance_fol(
        {
            "policies": [policy()],
            "transactions": [
                txn("T1", 6000, "Senior Manager"),
                txn("T2", 1000, "staff"),
            ],
        }
    )
    assert result["violations"] == []


def test_only_violating_transaction_is_reported():
    result = verify_compliance_fol(
        {
            "policies": [policy()],
            "transactions": [txn("T1", 6000, "Director"), txn("T2", 9000, "staff")],
        }
    )
    assert [v["transaction_id"] for v in result["violations"]] == ["T2"]


def test_inclusive_operator_boundary():
    knowledge = {"policies": [policy(op=">=")], "transactions": [txn("T1", 5000, "staff")]}
    assert len(verify_compliance_fol(knowledge)["violations"]) == 1
    knowledge = {"policies": [policy(op=">")], "transactions": [txn("T1", 5000, "staff")]}
    assert verify_compliance_fol(knowledge)["violations"] == []


def test_role_hierarchy_variants():
    assert role_level("Manager") == role_level("manager")
    assert role_level("Senior Manager") > role_level("manager")
    assert role_level("Director") > role_level("manager")
    assert role_level("totally unknown title") == -1


def test_contradictory_policies_are_flagged():
    result = verify_compliance_fol(
        {
            "policies": [
                policy("P1", threshold=5000, min_role="manager"),
                policy("P2", threshold=4000, min_role=None, max_role="supervisor"),
            ],
            "transactions": [],
        }
    )
    assert len(result["conflicts"]) == 1
    assert set(result["conflicts"][0]["policy_ids"]) == {"P1", "P2"}


def test_non_overlapping_policies_do_not_conflict():
    result = verify_compliance_fol(
        {
            "policies": [
                policy("P1", threshold=5000, op=">", min_role="manager"),
                policy("P2", threshold=1000, op="<=", min_role=None, max_role="supervisor"),
            ],
            "transactions": [],
        }
    )
    assert result["conflicts"] == []