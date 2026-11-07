"""Pydantic models: what the LLM extracts and what we insert into the database."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IssueType = Literal[
    "late_payment",
    "price_mismatch",
    "unpaid",
    "underpaid",
    "duplicate_payment",
    "due_date_mismatch",
]
Level = Literal["low", "medium", "high"]


class ContractTerms(BaseModel):
    """Terms extracted from a contract PDF by the LLM (floats keep the JSON schema simple)."""

    unit_price: float = Field(gt=0, description="Agreed price per unit, as a plain number, e.g. 12.5")
    currency: str = Field(min_length=3, max_length=3, description="3-letter currency code, e.g. USD")
    payment_days: int = Field(
        gt=0, le=365, description="N in 'net N days': days allowed to pay an invoice, from the payment terms clause"
    )
    late_penalty_pct: float = Field(
        ge=0, le=100, description="Late-payment penalty as a percentage number, e.g. 2 for 2%"
    )


class Issue(BaseModel):
    po_id: int
    type: IssueType
    severity: Level
    description: str = Field(min_length=1)
    amount_impact: float | None = None  # money at stake (penalty, overpayment, outstanding...)
    penalty: float | None = None  # contractual late-payment penalty, when relevant
    evidence: str = ""


class Report(BaseModel):
    supplier_id: int
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")
    summary: str = Field(min_length=1)
    issues: list[Issue] = Field(default_factory=list)
    risk_level: Level
