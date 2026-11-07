"""Read-only database access (uses the agent_reader role)."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..checks import period_bounds
from ..config import settings

MAX_ROWS = 200
_PG_OPTIONS = "-c statement_timeout=10000 -c default_transaction_read_only=on"

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do|execute|"
    r"vacuum|merge|set|reset|lock|pg_sleep|pg_read_file|lo_import|lo_export)\b",
    re.IGNORECASE,
)


class UnsafeSQLError(ValueError):
    pass


def validate_select(sql: str) -> str:
    """Accept one SELECT (or WITH ... SELECT) statement only; return it with a LIMIT."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("Empty SQL.")
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    if ";" in s:
        raise UnsafeSQLError("Only a single statement is allowed.")
    if "--" in s or "/*" in s:
        raise UnsafeSQLError("SQL comments are not allowed.")
    if not re.match(r"^(select|with)\b", s, re.IGNORECASE):
        raise UnsafeSQLError("Only SELECT statements are allowed.")
    m = _FORBIDDEN.search(s)
    if m:
        raise UnsafeSQLError(f"Forbidden keyword: {m.group(0).upper()}")
    if not re.search(r"\blimit\s+\d+", s, re.IGNORECASE):
        s += f" LIMIT {MAX_ROWS}"
    return s


def _run(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with psycopg.connect(settings.db_reader_url, row_factory=dict_row, options=_PG_OPTIONS) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def query_database(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Tool for the LLM: run one read-only SELECT. Raises UnsafeSQLError for anything else."""
    return _run(validate_select(sql), params)


def get_suppliers() -> list[dict[str, Any]]:
    return _run("SELECT id, name, country FROM suppliers ORDER BY id")


def get_period_data(supplier_id: int, period: str) -> list[dict[str, Any]]:
    """POs of a supplier that fall in the period (DB due date OR a payment inside the month),
    each with its payments attached under the key 'payments'."""
    start, end = period_bounds(period)
    pos = _run(
        """
        SELECT po.id, po.supplier_id, po.quantity, po.unit_price, po.amount,
               po.order_date, po.due_date, po.status
        FROM purchase_orders po
        WHERE po.supplier_id = %s
          AND ( (po.due_date >= %s AND po.due_date < %s)
                OR EXISTS (SELECT 1 FROM payments p
                           WHERE p.po_id = po.id AND p.paid_date >= %s AND p.paid_date < %s) )
        ORDER BY po.id
        """,
        (supplier_id, start, end, start, end),
    )
    if not pos:
        return []
    pays = _run(
        "SELECT po_id, amount_paid, paid_date FROM payments WHERE po_id = ANY(%s) ORDER BY paid_date, id",
        ([po["id"] for po in pos],),
    )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in pays:
        grouped[p["po_id"]].append(p)
    for po in pos:
        po["payments"] = grouped.get(po["id"], [])
    return pos
