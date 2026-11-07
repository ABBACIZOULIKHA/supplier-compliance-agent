# Practice dataset: Supplier Compliance Agent

1. Create the DB:  `createdb supplier_demo && psql -d supplier_demo -f sql/setup.sql`
2. Contracts are in `contracts/` (regenerate with `python generate_contracts.py`, needs reportlab, pillow, poppler).
3. `contract_tokyo_components.pdf` is an image-only scan: pdfplumber returns no text, so add an OCR step (pytesseract + pdf2image).
4. Roles created: `agent_reader` (SELECT only) for query_database, `agent_writer` (INSERT on compliance_reports only) for save_report.
5. Compare your agent's output with `ANSWER_KEY.md`.
