"""The ONLY write path: validate the report, then INSERT it (uses the agent_writer role)."""
from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..config import settings
from ..schemas import Report


def save_report(data: Report | dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Validate then insert into compliance_reports.

    Idempotent per (supplier_id, period): if a report already exists it is NOT inserted again
    (status 'skipped'). The writer role has no UPDATE/DELETE, so use force=True to add a newer
    row; history is kept and the newest created_at is the current report.
    Raises pydantic.ValidationError if the data is invalid.
    """
    report = data if isinstance(data, Report) else Report.model_validate(data)
    issues = json.loads(report.model_dump_json())["issues"]

    with psycopg.connect(settings.db_writer_url) as conn:
        with conn.cursor() as cur:
            if not force:
                cur.execute(
                    "SELECT id FROM compliance_reports WHERE supplier_id = %s AND period = %s LIMIT 1",
                    (report.supplier_id, report.period),
                )
                row = cur.fetchone()
                if row:
                    return {"status": "skipped", "id": row[0],
                            "reason": "report already exists for this supplier and period"}
            cur.execute(
                """INSERT INTO compliance_reports (supplier_id, period, summary, issues_json, risk_level)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (report.supplier_id, report.period, report.summary, Jsonb(issues), report.risk_level),
            )
            new_id = cur.fetchone()[0]
    return {"status": "inserted", "id": new_id}
