"""Two ways to produce the reports:
  * pipeline: Python orchestrates, the LLM only extracts contract terms and writes the summary (reliable)
  * agent:    the LLM drives the tools itself in a tool-calling loop (for learning; less accurate)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from . import llm
from .checks import as_of_date, compute_risk, period_bounds, run_checks
from .config import settings
from .notify import send_alert
from .prompts import AGENT_SYSTEM
from .schemas import Report
from .tools.db_tools import UnsafeSQLError, get_period_data, get_suppliers, query_database
from .tools.pdf_tools import find_contract, read_pdf
from .tools.save_tools import save_report

log = logging.getLogger(__name__)


# ============================================================== pipeline mode
def process_supplier(supplier: dict[str, Any], period: str, dry_run: bool = False,
                     force: bool = False) -> dict[str, Any]:
    sid, name = supplier["id"], supplier["name"]
    t0 = time.perf_counter()
    log.info("[%s] start supplier %s (%s)", period, sid, name)

    pos = get_period_data(sid, period)
    log.info("[%s] %s: %d purchase orders in period", period, name, len(pos))

    if not pos:
        issues, risk, used_ocr = [], "low", False
        summary = f"{name}, {period}: no purchase orders or payments in this period."
    else:
        contract = find_contract(name)
        pdf = read_pdf(contract)
        log.info("[%s] %s: read %s (%d pages, ocr=%s)", period, name, contract.name, pdf["pages"], pdf["used_ocr"])
        terms = llm.extract_contract_terms(pdf["text"])
        log.info("[%s] %s: contract terms %s", period, name, terms.model_dump())
        issues = run_checks(pos, terms, as_of_date(period))
        risk = compute_risk(issues)
        summary = llm.write_summary(name, period, issues, risk)

    report = Report(supplier_id=sid, period=period, summary=summary, issues=issues, risk_level=risk)

    save_result: dict[str, Any] = {"status": "dry-run"}
    if not dry_run:
        save_result = save_report(report, force=force)
        log.info("[%s] %s: save_report -> %s", period, name, save_result)
    if risk == "high" and save_result.get("status") != "skipped":
        send_alert(report, name)

    log.info("[%s] %s: done in %.1fs, risk=%s, issues=%d", period, name, time.perf_counter() - t0, risk, len(issues))
    return {"supplier": name, "report": report, "save": save_result}


def run_pipeline(period: str, supplier_id: int | None = None, dry_run: bool = False,
                 force: bool = False) -> list[dict[str, Any]]:
    results = []
    for s in get_suppliers():
        if supplier_id is not None and s["id"] != supplier_id:
            continue
        try:
            results.append(process_supplier(s, period, dry_run=dry_run, force=force))
        except Exception as e:  # noqa: BLE001 - one bad supplier must not stop the batch
            log.exception("[%s] supplier %s failed: %s", period, s["name"], e)
            results.append({"supplier": s["name"], "error": str(e)})
    return results


# ================================================================ agent mode
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "query_database",
        "description": "Run ONE read-only SQL SELECT on tables suppliers(id,name,country), "
                       "purchase_orders(id,supplier_id,quantity,unit_price,amount,order_date,due_date,status), "
                       "payments(id,po_id,amount_paid,paid_date). Returns rows as JSON.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "read_pdf",
        "description": "Return the full text of a contract PDF given its file path.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "save_report",
        "description": "Insert the final compliance report. Call once.",
        "parameters": {"type": "object", "properties": {"report": {"type": "object"}}, "required": ["report"]}}},
]


def _make_tools(dry_run: bool, force: bool):
    def t_query(sql: str) -> str:
        return json.dumps(query_database(sql), default=str)

    def t_pdf(path: str) -> str:
        return read_pdf(path)["text"]

    def t_save(report: dict) -> str:
        validated = Report.model_validate(report)  # raises -> error is sent back to the model
        if dry_run:
            return "dry-run: report is valid but was NOT saved:\n" + validated.model_dump_json(indent=1)
        return json.dumps(save_report(validated, force=force))

    return {"query_database": t_query, "read_pdf": t_pdf, "save_report": t_save}


def run_agent(period: str, supplier_id: int, dry_run: bool = False, force: bool = False) -> str:
    supplier = next((s for s in get_suppliers() if s["id"] == supplier_id), None)
    if supplier is None:
        raise ValueError(f"Unknown supplier id {supplier_id}")
    start, end = period_bounds(period)
    contract = find_contract(supplier["name"])
    tools = _make_tools(dry_run, force)

    messages: list[Any] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": (
            f"Audit supplier id {supplier['id']} ({supplier['name']}) for period {period}.\n"
            f"Period: {start} to {end} (exclusive). Judge 'overdue' as of {end}.\n"
            f"Include purchase orders whose due_date is in the period or that have a payment in the period.\n"
            f"Contract file: {contract}")},
    ]
    for step in range(1, settings.max_agent_steps + 1):
        msg = llm.chat(messages, tools=TOOL_SCHEMAS).message
        messages.append(msg)
        if not msg.tool_calls:
            log.info("agent finished in %d steps", step)
            return llm._clean(msg.content)
        for call in msg.tool_calls:
            name, args = call.function.name, call.function.arguments
            if isinstance(args, str):
                args = json.loads(args)
            print(f"  step {step}: {name}({json.dumps(args, default=str)[:160]})")
            try:
                result = tools[name](**args)
            except (UnsafeSQLError, ValidationError, FileNotFoundError, KeyError, TypeError, RuntimeError) as e:
                result = f"ERROR: {e}"
            except Exception as e:  # noqa: BLE001
                result = f"ERROR: {type(e).__name__}: {e}"
            log.info("agent tool %s -> %s", name, str(result)[:200].replace("\n", " "))
            messages.append({"role": "tool", "tool_name": name, "content": str(result)[:8000]})
    return f"Stopped after {settings.max_agent_steps} steps without a final answer."
