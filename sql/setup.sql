-- =====================================================================
-- Supplier Compliance Agent - practice database (PostgreSQL)
-- Usage:  createdb supplier_demo && psql -d supplier_demo -f sql/setup.sql
-- =====================================================================

DROP TABLE IF EXISTS compliance_reports, payments, purchase_orders, suppliers CASCADE;

CREATE TABLE suppliers (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    country TEXT NOT NULL
);

-- NOTE: quantity and unit_price were added to the original design so the
-- agent can actually check "price vs contract" per purchase order.
CREATE TABLE purchase_orders (
    id          INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    quantity    INTEGER NOT NULL,
    unit_price  NUMERIC(10,2) NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    order_date  DATE NOT NULL,
    due_date    DATE NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('open','partial','paid'))
);

CREATE TABLE payments (
    id          SERIAL PRIMARY KEY,
    po_id       INTEGER NOT NULL REFERENCES purchase_orders(id),
    amount_paid NUMERIC(12,2) NOT NULL,
    paid_date   DATE NOT NULL
);

CREATE TABLE compliance_reports (
    id          SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    period      TEXT NOT NULL,              -- e.g. '2026-10'
    summary     TEXT NOT NULL,
    issues_json JSONB NOT NULL DEFAULT '[]',
    risk_level  TEXT NOT NULL CHECK (risk_level IN ('low','medium','high')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- data
INSERT INTO suppliers (id, name, country) VALUES
 (1, 'Acme Industrial Supplies', 'US'),
 (2, 'Berlin Precision GmbH',    'DE'),
 (3, 'Nile Textiles',            'EG'),
 (4, 'Maghreb Logistics',        'DZ'),
 (5, 'Tokyo Components Ltd',     'JP');
SELECT setval('suppliers_id_seq', 5);

INSERT INTO purchase_orders
 (id, supplier_id, quantity, unit_price, amount, order_date, due_date, status) VALUES
 -- Acme (contract: 12.50/unit, net 30, 2% penalty)
 (1000, 1,  300, 12.50,  3750.00, '2026-08-10', '2026-09-09', 'paid'),
 (1001, 1,  400, 12.50,  5000.00, '2026-09-02', '2026-10-02', 'paid'),
 (1002, 1,  800, 12.50, 10000.00, '2026-09-10', '2026-10-10', 'paid'),
 (1003, 1,  200, 12.88,  2576.00, '2026-09-20', '2026-10-20', 'paid'),
 -- Berlin (contract: 48.00/unit, net 45, 1.5% penalty)
 (1004, 2,  100, 48.00,  4800.00, '2026-09-01', '2026-10-16', 'paid'),
 (1005, 2,  150, 48.00,  7200.00, '2026-09-15', '2026-10-30', 'paid'),
 -- Nile (contract: 7.80/unit, net 60, 3% penalty)
 (1006, 3, 5000,  7.80, 39000.00, '2026-08-20', '2026-10-19', 'open'),
 (1007, 3, 3000,  7.80, 23400.00, '2026-08-25', '2026-10-24', 'partial'),
 -- Maghreb (contract: 220.00/shipment, net 15, 2.5% penalty)
 (1008, 4,   10, 220.00,  2200.00, '2026-10-01', '2026-10-16', 'paid'),
 (1009, 4,   12, 220.00,  2640.00, '2026-10-10', '2026-10-25', 'paid'),
 (1010, 4,    8, 220.00,  1760.00, '2026-10-12', '2026-10-27', 'paid'),
 -- Tokyo (contract: 95.00/unit, net 30, 1% penalty)  [contract PDF is a scan]
 (1011, 5,   60,  95.00,  5700.00, '2026-09-25', '2026-10-25', 'paid'),
 (1012, 5,   40,  95.00,  3800.00, '2026-09-28', '2026-11-27', 'paid');

INSERT INTO payments (po_id, amount_paid, paid_date) VALUES
 (1000,  3750.00, '2026-09-25'),
 (1001,  5000.00, '2026-10-01'),
 (1002, 10000.00, '2026-10-27'),
 (1003,  2576.00, '2026-10-19'),
 (1004,  4800.00, '2026-10-14'),
 (1005,  7200.00, '2026-10-29'),
 -- 1006: no payment at all
 (1007, 15000.00, '2026-10-24'),
 (1008,  2200.00, '2026-10-20'),
 (1009,  2640.00, '2026-10-24'),
 (1009,  2640.00, '2026-10-26'),   -- duplicate payment
 (1010,  1000.00, '2026-10-27'),
 (1010,   760.00, '2026-10-27'),   -- split payment (fine)
 (1011,  5700.00, '2026-10-25'),
 (1012,  3800.00, '2026-10-30');

-- ------------------------------------------------- agent DB roles (safety)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_reader') THEN
    CREATE ROLE agent_reader LOGIN PASSWORD 'reader_pw';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_writer') THEN
    CREATE ROLE agent_writer LOGIN PASSWORD 'writer_pw';
  END IF;
END $$;

GRANT SELECT ON suppliers, purchase_orders, payments, compliance_reports TO agent_reader;
GRANT SELECT, INSERT ON compliance_reports TO agent_writer;
GRANT USAGE ON SEQUENCE compliance_reports_id_seq TO agent_writer;
