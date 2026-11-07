"""Compare the rule engine with ANSWER_KEY.md (no DB or LLM needed), plus an optional end-to-end run."""
import os
from datetime import date
from decimal import Decimal

import pytest

from agent.checks import as_of_date, compute_risk, run_checks
from agent.schemas import ContractTerms

AS_OF = as_of_date("2026-10")  # 2026-11-01


def po(id, qty, price, amount, order, due, payments):
    d = lambda s: date.fromisoformat(s)  # noqa: E731
    return {"id": id, "quantity": qty, "unit_price": Decimal(price), "amount": Decimal(amount),
            "order_date": d(order), "due_date": d(due),
            "payments": [{"amount_paid": Decimal(a), "paid_date": d(p)} for a, p in payments]}


TERMS = {
    "acme": ContractTerms(unit_price=12.50, currency="USD", payment_days=30, late_penalty_pct=2),
    "berlin": ContractTerms(unit_price=48.00, currency="USD", payment_days=45, late_penalty_pct=1.5),
    "nile": ContractTerms(unit_price=7.80, currency="USD", payment_days=60, late_penalty_pct=3),
    "maghreb": ContractTerms(unit_price=220.00, currency="USD", payment_days=15, late_penalty_pct=2.5),
    "tokyo": ContractTerms(unit_price=95.00, currency="USD", payment_days=30, late_penalty_pct=1),
}
POS = {
    "acme": [po(1001, 400, "12.50", "5000", "2026-09-02", "2026-10-02", [("5000", "2026-10-01")]),
             po(1002, 800, "12.50", "10000", "2026-09-10", "2026-10-10", [("10000", "2026-10-27")]),
             po(1003, 200, "12.88", "2576", "2026-09-20", "2026-10-20", [("2576", "2026-10-19")])],
    "berlin": [po(1004, 100, "48.00", "4800", "2026-09-01", "2026-10-16", [("4800", "2026-10-14")]),
               po(1005, 150, "48.00", "7200", "2026-09-15", "2026-10-30", [("7200", "2026-10-29")])],
    "nile": [po(1006, 5000, "7.80", "39000", "2026-08-20", "2026-10-19", []),
             po(1007, 3000, "7.80", "23400", "2026-08-25", "2026-10-24", [("15000", "2026-10-24")])],
    "maghreb": [po(1008, 10, "220.00", "2200", "2026-10-01", "2026-10-16", [("2200", "2026-10-20")]),
                po(1009, 12, "220.00", "2640", "2026-10-10", "2026-10-25",
                   [("2640", "2026-10-24"), ("2640", "2026-10-26")]),
                po(1010, 8, "220.00", "1760", "2026-10-12", "2026-10-27",
                   [("1000", "2026-10-27"), ("760", "2026-10-27")])],
    "tokyo": [po(1011, 60, "95.00", "5700", "2026-09-25", "2026-10-25", [("5700", "2026-10-25")]),
              po(1012, 40, "95.00", "3800", "2026-09-28", "2026-11-27", [("3800", "2026-10-30")])],
}


def issues(name):
    return run_checks(POS[name], TERMS[name], AS_OF)


def by(name, po_id, typ):
    found = [i for i in issues(name) if i.po_id == po_id and i.type == typ]
    assert len(found) == 1, f"expected one {typ} on PO {po_id}, got {found}"
    return found[0]


def test_acme_late_payment_and_penalty():
    i = by("acme", 1002, "late_payment")
    assert "17 days late" in i.description
    assert i.penalty == pytest.approx(200.00)


def test_acme_price_mismatch():
    i = by("acme", 1003, "price_mismatch")
    assert "3.04%" in i.description
    assert i.amount_impact == pytest.approx(76.00)  # (12.88 - 12.50) * 200
    assert {x.po_id for x in issues("acme")} == {1002, 1003}  # PO 1001 is clean
    assert compute_risk(issues("acme")) == "medium"


def test_berlin_is_clean():
    assert issues("berlin") == []
    assert compute_risk([]) == "low"


def test_nile_unpaid_and_underpaid():
    u = by("nile", 1006, "unpaid")
    assert "13 days overdue" in u.description
    assert u.penalty == pytest.approx(1170.00)
    assert by("nile", 1007, "underpaid").amount_impact == pytest.approx(8400.00)
    assert compute_risk(issues("nile")) == "high"


def test_maghreb_late_duplicate_and_split_ok():
    assert by("maghreb", 1008, "late_payment").penalty == pytest.approx(55.00)
    assert by("maghreb", 1009, "duplicate_payment").amount_impact == pytest.approx(2640.00)
    assert not [i for i in issues("maghreb") if i.po_id == 1010]  # split payment is fine
    assert compute_risk(issues("maghreb")) == "medium"


def test_tokyo_due_date_mismatch():
    i = by("tokyo", 1012, "due_date_mismatch")
    assert "2026-10-28" in i.description
    assert not [x for x in issues("tokyo") if x.po_id == 1011]
    assert compute_risk(issues("tokyo")) in {"low", "medium"}


# ------------------------------------------------------------------ pipeline without an LLM
def _regex_terms(text: str) -> ContractTerms:
    """Stand-in for the LLM so the whole pipeline (DB + PDF/OCR + checks) can be tested offline."""
    import re
    price = re.search(r"(\d+\.\d{2})\s*USD", text)
    days = re.search(r"net\s*(\d+)\s*days", text, re.I)
    pen = re.search(r"penalty\s+of\s*(\d+(?:\.\d+)?)\s*%", text, re.I)
    return ContractTerms(unit_price=float(price.group(1)), currency="USD",
                         payment_days=int(days.group(1)), late_penalty_pct=float(pen.group(1)))


def _db_up() -> bool:
    try:
        import psycopg
        from agent.config import settings
        psycopg.connect(settings.db_reader_url, connect_timeout=2).close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_up(), reason="practice database not reachable")
def test_pipeline_offline_matches_answer_key(monkeypatch):
    import shutil
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract needed for the scanned Tokyo contract")
    from agent import agent as agent_mod, llm
    monkeypatch.setattr(llm, "extract_contract_terms", _regex_terms)
    monkeypatch.setattr(llm, "write_summary", llm.deterministic_summary)
    res = {r["supplier"]: r["report"] for r in agent_mod.run_pipeline("2026-10", dry_run=True)}
    assert {k: v.risk_level for k, v in res.items()} == {
        "Acme Industrial Supplies": "medium", "Berlin Precision GmbH": "low", "Nile Textiles": "high",
        "Maghreb Logistics": "medium", "Tokyo Components Ltd": "medium"}
    assert {i.po_id for i in res["Acme Industrial Supplies"].issues} == {1002, 1003}  # PO 1000 (Sept) excluded


# ------------------------------------------------------------------ optional end-to-end
@pytest.mark.e2e
@pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 (needs DB + Ollama)")
def test_pipeline_matches_answer_key():
    from agent.agent import run_pipeline
    res = {r["supplier"]: r["report"].risk_level for r in run_pipeline("2026-10", dry_run=True)}
    assert res["Acme Industrial Supplies"] == "medium"
    assert res["Berlin Precision GmbH"] == "low"
    assert res["Nile Textiles"] == "high"
    assert res["Maghreb Logistics"] == "medium"
    assert res["Tokyo Components Ltd"] in {"low", "medium"}
