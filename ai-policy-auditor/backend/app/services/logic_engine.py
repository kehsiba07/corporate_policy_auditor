import logging
import re
from itertools import combinations

# pyrefly: ignore [missing-import]
from z3 import (
    And,
    Bool,
    BoolVal,
    Const,
    DeclareSort,
    Distinct,
    ForAll,
    Function,
    Implies,
    Int,
    IntSort,
    IntVal,
    Or,
    Real,
    RealSort,
    RealVal,
    Solver,
    unknown,
    unsat,
    sat,
)

logger = logging.getLogger(__name__)

# Role hierarchy: higher number = more authority.
ROLE_LEVELS = {
    "intern": 0,
    "staff": 1,
    "employee": 1,
    "associate": 1,
    "analyst": 1,
    "senior staff": 2,
    "senior analyst": 2,
    "team lead": 3,
    "supervisor": 3,
    "assistant manager": 3,
    "manager": 4,
    "senior manager": 5,
    "director": 6,
    "senior director": 7,
    "vice president": 8,
    "vp": 8,
    "cfo": 9,
    "coo": 9,
    "cto": 9,
    "ceo": 10,
}
MAX_LEVEL = max(ROLE_LEVELS.values())
UNKNOWN_LEVEL = -1

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def normalize_role(role) -> str:
    return re.sub(r"[\s_\-]+", " ", str(role or "")).strip().lower()


def role_level(role) -> int:
    """Exact match first, then the longest known title contained in the string."""
    name = normalize_role(role)
    if not name:
        return UNKNOWN_LEVEL
    if name in ROLE_LEVELS:
        return ROLE_LEVELS[name]
    for title in sorted(ROLE_LEVELS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(title)}\b", name):
            return ROLE_LEVELS[title]
    return UNKNOWN_LEVEL


def _condition(operator, amount_term, threshold):
    if threshold is None:
        return BoolVal(True)
    return _OPS[operator](amount_term, RealVal(threshold))


def _requirement(level_term, min_level, max_level):
    parts = []
    if min_level is not None:
        parts.append(level_term >= min_level)
    if max_level is not None:
        parts.append(level_term <= max_level)
    return And(parts) if parts else BoolVal(True)


def _compile_policies(policies):
    """Turns raw policy dicts into (policy, min_level, max_level); skips uncheckable ones."""
    compiled, warnings = [], []
    for p in policies:
        operator = p.get("operator", ">")
        if operator not in _OPS:
            warnings.append(f"Policy {p.get('id')} skipped: unsupported operator '{operator}'.")
            continue

        min_role, max_role = p.get("min_approver_role"), p.get("max_approver_role")
        min_level = role_level(min_role) if min_role else None
        max_level = role_level(max_role) if max_role else None

        if min_role and min_level == UNKNOWN_LEVEL:
            warnings.append(f"Policy {p.get('id')} skipped: unknown role '{min_role}'.")
            continue
        if max_role and max_level == UNKNOWN_LEVEL:
            warnings.append(f"Policy {p.get('id')} skipped: unknown role '{max_role}'.")
            continue
        if min_level is None and max_level is None:
            warnings.append(
                f"Policy {p.get('id')} has no approver requirement and cannot be machine-checked."
            )
            continue
        compiled.append((p, min_level, max_level))
    return compiled, warnings


def _check_policy_set(items, require_overlap_first=False):
    """
    CSP over (amount, approver_level): can ALL given policies be satisfied together
    for an amount where they all apply? Returns the unsat core (labels) or None if consistent.
    """
    amount = Real("amount")
    level = Int("approver_level")

    if require_overlap_first and len(items) > 1:
        overlap = Solver()
        for p, _mn, _mx in items:
            overlap.add(_condition(p.get("operator", ">"), amount, p.get("threshold")))
        overlap.add(amount >= 0)
        if overlap.check() != sat:
            return None  # policies never apply at the same time

    solver = Solver()
    solver.add(amount >= 0, level >= 0, level <= MAX_LEVEL)
    for p, mn, mx in items:
        pid = p["id"]
        solver.assert_and_track(
            _condition(p.get("operator", ">"), amount, p.get("threshold")), f"applies:{pid}"
        )
        solver.assert_and_track(_requirement(level, mn, mx), f"requires:{pid}")

    if solver.check() == unsat:
        return sorted(str(c) for c in solver.unsat_core())
    return None


def find_policy_conflicts(compiled) -> list:
    conflicts = []

    for p, mn, mx in compiled:
        core = _check_policy_set([(p, mn, mx)])
        if core is not None:
            conflicts.append(
                {
                    "policy_ids": [p["id"]],
                    "reason": f"Policy {p['id']} is unsatisfiable on its own (minimum role is above maximum role).",
                    "unsat_core": core,
                }
            )

    for a, b in combinations(compiled, 2):
        core = _check_policy_set([a, b], require_overlap_first=True)
        if core is not None:
            ids = [a[0]["id"], b[0]["id"]]
            conflicts.append(
                {
                    "policy_ids": ids,
                    "reason": (
                        f"Policies {ids[0]} and {ids[1]} apply to the same transactions "
                        "but impose approver requirements that cannot both be met."
                    ),
                    "unsat_core": core,
                }
            )
    return conflicts


def _describe_core(core, policies_by_flag, txn_labels):
    out = []
    for name in core:
        out.append(policies_by_flag.get(name) or txn_labels.get(name) or name)
    return out


def check_transactions(compiled, transactions):
    """
    One solver, one finite domain of transactions, policies as ForAll axioms.
    For every (policy, transaction) pair, assume the policy plus that transaction's facts;
    UNSAT means the facts contradict the policy, and the unsat core cites exactly which
    policy and facts are responsible.
    """
    violations, warnings = [], []
    if not compiled or not transactions:
        return violations, warnings

    Txn = DeclareSort("Txn")
    Amount = Function("Amount", Txn, RealSort())
    ApproverLevel = Function("ApproverLevel", Txn, IntSort())

    solver = Solver()
    consts = [Const(f"txn_{i}", Txn) for i in range(len(transactions))]
    if len(consts) > 1:
        solver.add(Distinct(*consts))
    x = Const("x", Txn)
    solver.add(ForAll([x], Or([x == c for c in consts])))  # domain closure

    amount_flags, level_flags, txn_labels = [], [], {}
    for i, (txn, const) in enumerate(zip(transactions, consts)):
        level = role_level(txn.get("approved_by_role"))
        if level == UNKNOWN_LEVEL:
            warnings.append(
                f"Transaction {txn['id']}: approver role '{txn.get('approved_by_role')}' "
                "is missing or unrecognized and is treated as unauthorized."
            )
        a_flag, l_flag = Bool(f"fact_amount_{i}"), Bool(f"fact_approver_{i}")
        solver.add(Implies(a_flag, Amount(const) == RealVal(txn["amount"])))
        solver.add(Implies(l_flag, ApproverLevel(const) == IntVal(level)))
        amount_flags.append(a_flag)
        level_flags.append(l_flag)
        txn_labels[str(a_flag)] = f"fact: {txn['id']} amount = {txn['amount']:,.2f}"
        txn_labels[str(l_flag)] = (
            f"fact: {txn['id']} approved by '{txn.get('approved_by_role')}' (level {level})"
        )

    policy_flags, policy_labels = [], {}
    for j, (p, mn, mx) in enumerate(compiled):
        flag = Bool(f"policy_{j}")
        rule = ForAll(
            [x],
            Implies(
                _condition(p.get("operator", ">"), Amount(x), p.get("threshold")),
                _requirement(ApproverLevel(x), mn, mx),
            ),
        )
        solver.add(Implies(flag, rule))
        policy_flags.append(flag)
        policy_labels[str(flag)] = f"policy: {p['id']}"

    for j, (p, mn, mx) in enumerate(compiled):
        for i, txn in enumerate(transactions):
            result = solver.check(policy_flags[j], amount_flags[i], level_flags[i])
            if result == unknown:
                warnings.append(
                    f"Solver could not decide policy {p['id']} for transaction {txn['id']}."
                )
                continue
            if result != unsat:
                continue

            core = _describe_core(
                [str(c) for c in solver.unsat_core()], policy_labels, txn_labels
            )
            approver_level = role_level(txn.get("approved_by_role"))
            threshold = p.get("threshold")
            op = p.get("operator", ">")

            reasons = []
            if mn is not None and approver_level < mn:
                reasons.append(
                    f"requires approval by at least '{p.get('min_approver_role')}' (level {mn})"
                )
            if mx is not None and approver_level > mx:
                reasons.append(
                    f"allows approval by at most '{p.get('max_approver_role')}' (level {mx})"
                )
            applies = (
                f"amount {txn['amount']:,.2f} {op} {threshold:,.2f}"
                if threshold is not None
                else "it applies to all transactions"
            )
            explanation = (
                f"Policy {p['id']} applies ({applies}) and {' and '.join(reasons)}, "
                f"but {txn['id']} was approved by '{txn.get('approved_by_role') or 'unknown'}' "
                f"(level {approver_level})."
            )

            violations.append(
                {
                    "policy_id": p["id"],
                    "transaction_id": txn["id"],
                    "amount": txn["amount"],
                    "threshold": threshold,
                    "operator": op,
                    "approver_role": txn.get("approved_by_role"),
                    "approver_level": approver_level,
                    "required_role": p.get("min_approver_role"),
                    "required_level": mn,
                    "max_role": p.get("max_approver_role"),
                    "max_level": mx,
                    "explanation": explanation,
                    "unsat_core": core,
                    "policy_quote": p.get("source_quote"),
                    "policy_page": p.get("page"),
                    "transaction_quote": txn.get("source_quote"),
                    "transaction_page": txn.get("page"),
                }
            )
    return violations, warnings


def verify_compliance_fol(knowledge: dict) -> dict:
    """
    Entry point. Returns {"violations": [...], "conflicts": [...], "warnings": [...]}.
    """
    policies = knowledge.get("policies", [])
    transactions = knowledge.get("transactions", [])

    compiled, warnings = _compile_policies(policies)
    conflicts = find_policy_conflicts(compiled)
    violations, txn_warnings = check_transactions(compiled, transactions)

    return {
        "violations": violations,
        "conflicts": conflicts,
        "warnings": warnings + txn_warnings,
    }