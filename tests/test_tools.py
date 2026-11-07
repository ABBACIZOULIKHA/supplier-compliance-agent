import shutil

import pytest
from pydantic import ValidationError

from agent.config import ROOT, settings
from agent.schemas import Report
from agent.tools.db_tools import UnsafeSQLError, validate_select
from agent.tools.pdf_tools import find_contract, read_pdf

CONTRACTS = ROOT / "data" / "contracts"


def _db_available() -> bool:
    try:
        import psycopg
        psycopg.connect(settings.db_reader_url, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="practice database not reachable")


# ---------------------------------------------------------------- SQL guard
@pytest.mark.parametrize("sql", [
    "DELETE FROM payments",
    "UPDATE purchase_orders SET amount = 0",
    "DROP TABLE suppliers",
    "SELECT 1; DROP TABLE suppliers",
    "INSERT INTO compliance_reports VALUES (1)",
    "WITH x AS (DELETE FROM payments RETURNING *) SELECT * FROM x",
    "SELECT pg_sleep(100)",
    "SELECT * FROM suppliers -- comment",
    "",
])
def test_guard_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSQLError):
        validate_select(sql)


def test_guard_accepts_select_and_adds_limit():
    assert validate_select("SELECT * FROM suppliers;").endswith("LIMIT 200")
    assert validate_select("select * from payments limit 5") == "select * from payments limit 5"
    assert validate_select("WITH a AS (SELECT 1) SELECT * FROM a").startswith("WITH")


@needs_db
def test_query_database_runs_select_and_reader_cannot_write():
    import psycopg
    from agent.tools.db_tools import query_database
    assert len(query_database("SELECT * FROM suppliers")) == 5
    with pytest.raises(psycopg.Error):  # defense in depth: the role itself is read-only
        with psycopg.connect(settings.db_reader_url) as c:
            c.execute("DELETE FROM payments")


# ---------------------------------------------------------------- PDF
def test_find_contract_by_supplier_name():
    assert find_contract("Acme Industrial Supplies").name == "contract_acme.pdf"
    assert find_contract("Berlin Precision GmbH").name == "contract_berlin_precision.pdf"
    assert find_contract("Tokyo Components Ltd").name == "contract_tokyo_components.pdf"
    with pytest.raises(FileNotFoundError):
        find_contract("Unknown Corp")


def test_read_pdf_text_layer_no_ocr():
    r = read_pdf(CONTRACTS / "contract_acme.pdf")
    assert r["used_ocr"] is False
    assert "net 30 days" in r["text"] and "12.50" in r["text"]


@pytest.mark.skipif(shutil.which("tesseract") is None or shutil.which("pdftoppm") is None,
                    reason="tesseract/poppler not installed")
def test_read_pdf_scanned_uses_ocr():
    r = read_pdf(CONTRACTS / "contract_tokyo_components.pdf")
    assert r["used_ocr"] is True
    import re
    assert re.search(r"net\s*30", r["text"], re.I)


# ---------------------------------------------------------------- save_report
def test_report_rejects_invalid_risk_level():
    with pytest.raises(ValidationError):
        Report(supplier_id=1, period="2026-10", summary="x", issues=[], risk_level="critical")


def test_report_rejects_bad_period():
    with pytest.raises(ValidationError):
        Report(supplier_id=1, period="10/2026", summary="x", issues=[], risk_level="low")


@needs_db
def test_save_report_inserts_and_is_idempotent(monkeypatch):
    """Runs inside one transaction that is rolled back, so your database is left untouched."""
    import psycopg
    from agent.tools import save_tools

    conn = psycopg.connect(settings.db_writer_url)

    class _KeepOpen:  # lets save_report use our connection without committing/closing it
        def __enter__(self):
            return conn

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(save_tools.psycopg, "connect", lambda *a, **k: _KeepOpen())
    try:
        rep = Report(supplier_id=2, period="1999-01", summary="test", issues=[], risk_level="low")
        assert save_tools.save_report(rep)["status"] == "inserted"
        assert save_tools.save_report(rep)["status"] == "skipped"
        assert save_tools.save_report(rep, force=True)["status"] == "inserted"
    finally:
        conn.rollback()
        conn.close()
