"""Deterministic compliance rules. NO LLM here: the small model must not do math or date logic.

Risk rules (tune the constants below):
  * every issue has a severity (unpaid/underpaid = high, late/price/duplicate = medium,
    due_date_mismatch = low; a payment more than VERY_LATE_DAYS late is high)
  * report risk = worst severity among the issues
  * a report that would be 'medium' becomes 'high' if the total money impact >= HIGH_IMPACT_THRESHOLD
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .schemas import ContractTerms, Issue

HIGH_IMPACT_THRESHOLD = Decimal("10000")
VERY_LATE_DAYS = 30
_RANK = {"low": 0, "medium": 1, "high": 2}
_LEVEL = {v: k for k, v in _RANK.items()}
_CENT = Decimal("0.01")


def money(x: Decimal | float | int | str) -> Decimal:
    return Decimal(str(x)).quantize(_CENT, ROUND_HALF_UP)


def period_bounds(period: str) -> tuple[date, date]:
    """'2026-10' -> (2026-10-01, 2026-11-01)."""
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def as_of_date(period: str) -> date:
    """Date used to judge 'overdue': the first day after the period."""
    return period_bounds(period)[1]


def expected_due_date(order_date: date, payment_days: int) -> date:
    return order_date + timedelta(days=payment_days)


def check_po(po: dict[str, Any], terms: ContractTerms, as_of: date) -> list[Issue]:
    issues: list[Issue] = []
    po_id = po["id"]
    amount = Decimal(po["amount"])
    pct = Decimal(str(terms.late_penalty_pct))
    penalty = money(amount * pct / 100)
    expected_due = expected_due_date(po["order_date"], terms.payment_days)
    payments = sorted(po.get("payments", []), key=lambda p: p["paid_date"])
    total_paid = sum((Decimal(p["amount_paid"]) for p in payments), Decimal("0"))

    # date on which cumulative payments first covered the full amount
    settled_on, running = None, Decimal("0")
    for p in payments:
        running += Decimal(p["amount_paid"])
        if running >= amount:
            settled_on = p["paid_date"]
            break

    due_txt = f"due {expected_due} (order {po['order_date']} + {terms.payment_days}d)"

    if not payments:
        if as_of > expected_due:
            days = (as_of - expected_due).days
            issues.append(Issue(
                po_id=po_id, type="unpaid", severity="high",
                description=(f"PO {po_id} is unpaid and {days} days overdue as of {as_of}. "
                             f"Outstanding {money(amount)}; contractual penalty {penalty} ({pct}%)."),
                amount_impact=float(money(amount)), penalty=float(penalty), evidence=due_txt + ", no payment",
            ))
    elif total_paid < amount:
        outstanding = money(amount - total_paid)
        over = (as_of - expected_due).days if as_of > expected_due else 0
        issues.append(Issue(
            po_id=po_id, type="underpaid", severity="high",
            description=(f"PO {po_id} is underpaid: {money(total_paid)} paid of {money(amount)}, "
                         f"{outstanding} outstanding" + (f" and {over} days overdue." if over else ".")),
            amount_impact=float(outstanding), evidence=due_txt + f", paid {money(total_paid)}",
        ))
    else:
        if settled_on and settled_on > expected_due:
            days = (settled_on - expected_due).days
            issues.append(Issue(
                po_id=po_id, type="late_payment",
                severity="high" if days > VERY_LATE_DAYS else "medium",
                description=(f"PO {po_id} was paid {days} days late (due {expected_due}, paid {settled_on}). "
                             f"A {pct}% penalty of {penalty} applies under the contract."),
                amount_impact=float(penalty), penalty=float(penalty), evidence=due_txt + f", paid {settled_on}",
            ))
        if total_paid > amount:
            extra = money(total_paid - amount)
            issues.append(Issue(
                po_id=po_id, type="duplicate_payment", severity="medium",
                description=f"PO {po_id} was overpaid by {extra}: {money(total_paid)} paid for an amount of {money(amount)}.",
                amount_impact=float(extra), evidence=f"{len(payments)} payments totalling {money(total_paid)}",
            ))

    # price vs contract
    contract_price = Decimal(str(terms.unit_price))
    po_price = Decimal(po["unit_price"])
    if po_price != contract_price:
        diff_pct = ((po_price - contract_price) / contract_price * 100).quantize(_CENT, ROUND_HALF_UP)
        impact = money((po_price - contract_price) * po["quantity"])
        way = "above" if po_price > contract_price else "below"
        issues.append(Issue(
            po_id=po_id, type="price_mismatch", severity="medium",
            description=(f"PO {po_id} unit price {money(po_price)} is {abs(diff_pct)}% {way} the contract price "
                         f"{money(contract_price)} ({impact} on {po['quantity']} units)."),
            amount_impact=float(abs(impact)), evidence=f"PO {po_price} vs contract {contract_price}",
        ))

    # due date stored in DB vs contract terms
    if po["due_date"] != expected_due:
        issues.append(Issue(
            po_id=po_id, type="due_date_mismatch", severity="low",
            description=(f"PO {po_id} has due date {po['due_date']} in the database but the contract "
                         f"(net {terms.payment_days}) gives {expected_due}."),
            evidence=f"db due {po['due_date']} vs expected {expected_due}",
        ))
    return issues


def run_checks(pos: list[dict[str, Any]], terms: ContractTerms, as_of: date) -> list[Issue]:
    out: list[Issue] = []
    for po in pos:
        out.extend(check_po(po, terms, as_of))
    return sorted(out, key=lambda i: (i.po_id, i.type))


def compute_risk(issues: list[Issue]) -> str:
    if not issues:
        return "low"
    worst = max(_RANK[i.severity] for i in issues)
    total = sum((Decimal(str(i.amount_impact or 0)) for i in issues), Decimal("0"))
    if worst < _RANK["high"] and total >= HIGH_IMPACT_THRESHOLD:
        worst = _RANK["high"]
    return _LEVEL[worst]
