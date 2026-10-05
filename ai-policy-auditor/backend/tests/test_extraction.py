import asyncio
import json
from types import SimpleNamespace

# pyrefly: ignore [missing-import]
import pytest
from pydantic import ValidationError

from app.schemas import Policy
from app.services.extraction import (
    ExtractionError,
    chunk_text,
    extract_knowledge,
    verify_quotes,
)

DOC = (
    "=== PAGE 1 ===\n"
    "Section 4: Transactions over 5000 require manager approval.\n"
    "=== PAGE 2 ===\n"
    "Transaction TX-9 for 6000 was approved by a staff member.\n"
)

GOOD = {
    "policies": [
        {
            "id": "P1",
            "description": "Large transactions need a manager",
            "threshold": 5000,
            "operator": ">",
            "min_approver_role": "manager",
            "max_approver_role": None,
            "source_quote": "Transactions over 5000 require manager approval.",
        }
    ],
    "transactions": [
        {
            "id": "TX-9",
            "amount": 6000,
            "employee_role": None,
            "approved_by_role": "staff",
            "source_quote": "Transaction TX-9 for 6000 was approved by a staff member.",
        }
    ],
}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls += 1
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def test_schema_rejects_invalid_operator():
    with pytest.raises(ValidationError):
        Policy(id="P1", description="x", operator="~", source_quote="q")


def test_schema_normalizes_operator_aliases():
    p = Policy(id="P1", description="x", operator="≥", source_quote="q")
    assert p.operator == ">="


def test_bad_json_triggers_retry_then_succeeds():
    client = FakeClient(["this is not json", json.dumps(GOOD)])
    result = asyncio.run(extract_knowledge(DOC, client=client))
    assert client.calls == 2
    assert len(result["policies"]) == 1
    assert len(result["transactions"]) == 1


def test_repeated_bad_output_raises():
    client = FakeClient(["nope", "still nope", "{bad"])
    with pytest.raises(ExtractionError):
        asyncio.run(extract_knowledge(DOC, client=client))
    assert client.calls == 3


def test_hallucinated_quote_is_discarded():
    bad = json.loads(json.dumps(GOOD))
    bad["policies"][0]["source_quote"] = "Everything above 100 needs the CEO to sign."
    client = FakeClient([json.dumps(bad)])
    result = asyncio.run(extract_knowledge(DOC, client=client))
    assert result["policies"] == []
    assert any("not found" in w for w in result["warnings"])
    assert len(result["transactions"]) == 1


def test_quote_verification_sets_actual_page():
    from app.schemas import ExtractionPayload

    payload = ExtractionPayload.model_validate(GOOD)
    kept, warnings = verify_quotes(payload.policies, DOC, "policy")
    assert warnings == []
    assert kept[0].page == 1
    kept_t, _ = verify_quotes(payload.transactions, DOC, "transaction")
    assert kept_t[0].page == 2


def test_chunking_splits_long_documents_on_page_boundaries():
    pages = "".join(f"=== PAGE {i} ===\n{'word ' * 400}\n" for i in range(1, 8))
    chunks = chunk_text(pages, max_chars=3000)
    assert len(chunks) > 1
    assert all(len(c) <= 3200 for c in chunks)