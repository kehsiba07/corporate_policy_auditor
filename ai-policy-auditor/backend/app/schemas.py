import time
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_OPERATOR_ALIASES = {
    "≥": ">=",
    "≤": "<=",
    "=": "==",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "==",
}


class Policy(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, extra="ignore")

    id: str
    description: str
    threshold: Optional[float] = None
    operator: Literal[">", ">=", "<", "<=", "=="] = ">"
    min_approver_role: Optional[str] = None
    max_approver_role: Optional[str] = None
    source_quote: str
    page: Optional[int] = None

    @field_validator("operator", mode="before")
    @classmethod
    def _normalize_operator(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return _OPERATOR_ALIASES.get(v.lower(), v)
        return v


class Transaction(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, extra="ignore")

    id: str
    amount: float
    employee_role: Optional[str] = None
    approved_by_role: Optional[str] = None
    source_quote: str
    page: Optional[int] = None


class ExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    policies: List[Policy] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)


class Violation(BaseModel):
    policy_id: str
    transaction_id: str
    amount: float
    threshold: Optional[float] = None
    operator: str = ">"
    approver_role: Optional[str] = None
    approver_level: int = -1
    required_role: Optional[str] = None
    required_level: Optional[int] = None
    max_role: Optional[str] = None
    max_level: Optional[int] = None
    explanation: str
    unsat_core: List[str] = Field(default_factory=list)
    policy_quote: Optional[str] = None
    policy_page: Optional[int] = None
    transaction_quote: Optional[str] = None
    transaction_page: Optional[int] = None
    risk_score: float = 0.0
    severity: str = "Low"
    rank: int = 0


class Conflict(BaseModel):
    policy_ids: List[str]
    reason: str
    unsat_core: List[str] = Field(default_factory=list)


class AuditResult(BaseModel):
    report_markdown: str
    violations: List[Violation] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    policy_count: int = 0
    transaction_count: int = 0


class LogMessage(BaseModel):
    type: Literal["log"] = "log"
    message: str
    ts: float = Field(default_factory=time.time)


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    ts: float = Field(default_factory=time.time)


class ReportMessage(BaseModel):
    type: Literal["report"] = "report"
    report: AuditResult
    ts: float = Field(default_factory=time.time)