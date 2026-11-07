# Answer key (period = 2026-10) — use it to test your agent

Contracts are with "Globex Manufacturing Inc." (the buyer). Terms: net N days from PO order date, one-time late penalty % of invoice.

| Supplier | Contract | Expected issues | Expected risk |
|---|---|---|---|
| 1 Acme | 12.50/unit, net 30, 2% | PO 1002 paid 17 days late (due 10-10, paid 10-27) -> penalty 2% = 200.00 not paid. PO 1003 unit price 12.88 = 3.04% above contract (+76.00 = 0.38 x 200 units). PO 1000 is late too but belongs to September (outside period). | medium |
| 2 Berlin | 48.00/unit, net 45, 1.5% | None. | low |
| 3 Nile | 7.80/unit, net 60, 3% | PO 1006 unpaid, 13 days overdue on 11-01 (39,000.00; penalty 1,170.00). PO 1007 underpaid: 15,000 of 23,400 (8,400 outstanding, status partial). | high |
| 4 Maghreb | 220/shipment, net 15, 2.5% | PO 1008 paid 4 days late (due 10-16, paid 10-20) -> penalty 55.00. PO 1009 duplicate payment (2,640.00 paid twice). PO 1010 split payment = OK (not an issue). | medium |
| 5 Tokyo | 95/unit, net 30, 1% | PO 1012 due_date in DB (11-27) is 60 days after order, contract says net 30 (should be 10-28). Paid 10-30 = 2 days late vs contract. Contract is a SCANNED PDF -> needs OCR. | low/medium |
