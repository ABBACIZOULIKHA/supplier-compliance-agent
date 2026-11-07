"""CLI:  python -m agent.main --period 2026-10 [--supplier-id 1] [--mode pipeline|agent] [--dry-run] [--force]"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date, datetime

from .config import settings


def previous_period(today: date | None = None) -> str:
    today = today or date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{y}-{m:02d}"


def setup_logging() -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    file_h = logging.FileHandler(settings.log_dir / f"agent_{datetime.now():%Y%m%d}.log", encoding="utf-8")
    file_h.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)  # console stays quiet; details go to the log file
    logging.basicConfig(level=logging.INFO, handlers=[file_h, console])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Supplier contract & payment compliance agent")
    p.add_argument("--period", default=None, help="YYYY-MM (default: previous month)")
    p.add_argument("--supplier-id", type=int, default=None)
    p.add_argument("--mode", choices=["pipeline", "agent"], default="pipeline")
    p.add_argument("--dry-run", action="store_true", help="print reports, do not write to the database")
    p.add_argument("--force", action="store_true", help="insert even if a report for this supplier/period exists")
    args = p.parse_args(argv)

    period = args.period or previous_period()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        p.error("--period must look like 2026-10")
    setup_logging()
    log = logging.getLogger("agent.main")
    log.info("run started: period=%s mode=%s supplier=%s dry_run=%s", period, args.mode, args.supplier_id, args.dry_run)

    from . import agent  # imported late so --help works without DB/LLM

    if args.mode == "agent":
        if args.supplier_id is None:
            p.error("--mode agent needs --supplier-id (the free-form agent handles one supplier at a time)")
        print(agent.run_agent(period, args.supplier_id, dry_run=args.dry_run, force=args.force))
        return 0

    failures = 0
    for r in agent.run_pipeline(period, args.supplier_id, dry_run=args.dry_run, force=args.force):
        if "error" in r:
            failures += 1
            print(f"\n[FAILED] {r['supplier']}: {r['error']}")
            continue
        rep = r["report"]
        print(f"\n=== {r['supplier']} | {rep.period} | risk: {rep.risk_level.upper()} | {r['save']['status']}")
        print(rep.summary)
        for i in rep.issues:
            print(f"  - [{i.severity}] {i.type}: {i.description}")
    log.info("run finished, %d failure(s)", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
