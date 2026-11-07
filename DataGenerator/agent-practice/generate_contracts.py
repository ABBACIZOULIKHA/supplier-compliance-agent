"""Generates 5 supplier contract PDFs into ./contracts (Tokyo one is a 'scan')."""
import os, subprocess, random, glob
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from PIL import Image, ImageFilter

OUT = "contracts"
os.makedirs(OUT, exist_ok=True)
S = getSampleStyleSheet()

SUPPLIERS = [
  dict(file="contract_acme.pdf", name="Acme Industrial Supplies", country="United States",
       product="Industrial fasteners (box of 100)", price="12.50", cur="USD", unit="box",
       days=30, pen="2", ref="ACM-2025-014", date="January 15, 2025", scan=False),
  dict(file="contract_berlin_precision.pdf", name="Berlin Precision GmbH", country="Germany",
       product="CNC machined bearings", price="48.00", cur="USD", unit="piece",
       days=45, pen="1.5", ref="BPG-2025-007", date="March 3, 2025", scan=False),
  dict(file="contract_nile_textiles.pdf", name="Nile Textiles", country="Egypt",
       product="Cotton fabric roll (50 m)", price="7.80", cur="USD", unit="roll",
       days=60, pen="3", ref="NLT-2024-031", date="November 20, 2024", scan=False),
  dict(file="contract_maghreb_logistics.pdf", name="Maghreb Logistics", country="Algeria",
       product="Freight shipment (container, Algiers-Marseille)", price="220.00", cur="USD", unit="shipment",
       days=15, pen="2.5", ref="MGL-2026-002", date="February 9, 2026", scan=False),
  dict(file="contract_tokyo_components.pdf", name="Tokyo Components Ltd", country="Japan",
       product="Electronic control modules", price="95.00", cur="USD", unit="unit",
       days=30, pen="1", ref="TKC-2025-022", date="June 1, 2025", scan=True),
]

def build(s, path):
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=60, rightMargin=60, topMargin=60, bottomMargin=60)
    h, b = S["Heading2"], S["BodyText"]
    st = []
    st.append(Paragraph("SUPPLY AGREEMENT", S["Title"]))
    st.append(Paragraph(f"Contract Reference: {s['ref']}", b))
    st.append(Spacer(1, 10))
    st.append(Paragraph(
        f"This Supply Agreement (the \"Agreement\") is made on {s['date']} between "
        f"<b>Globex Manufacturing Inc.</b> (the \"Buyer\") and <b>{s['name']}</b>, "
        f"a company registered in {s['country']} (the \"Supplier\").", b))
    st.append(Paragraph("1. Scope of Supply", h))
    st.append(Paragraph(f"The Supplier agrees to supply <b>{s['product']}</b> to the Buyer upon receipt of "
        "written purchase orders. Delivery schedules are specified in each purchase order.", b))
    st.append(Paragraph("2. Pricing", h))
    st.append(Paragraph("The unit price applicable to all purchase orders during the term of this Agreement is:", b))
    t = Table([["Item", "Unit", "Agreed Unit Price"],
               [s["product"], s["unit"], f"{s['price']} {s['cur']}"]], colWidths=[250, 80, 130])
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey)]))
    st += [Spacer(1,6), t, Spacer(1,6)]
    st.append(Paragraph("Prices are fixed for the full term and may only be changed by a written amendment "
        "signed by both parties. Prices are exclusive of VAT.", b))
    st.append(Paragraph("3. Payment Terms", h))
    st.append(Paragraph(f"The Buyer shall pay each invoice within <b>net {s['days']} days</b> from the purchase order date. "
        "Payment is made by bank transfer. Partial payments are permitted but do not extend the due date for the "
        "remaining balance.", b))
    st.append(PageBreak())
    st.append(Paragraph("4. Late Payment Penalty", h))
    st.append(Paragraph(f"If the Buyer fails to pay an invoice by its due date, the Supplier is entitled to a one-time "
        f"late-payment penalty of <b>{s['pen']}%</b> of the overdue invoice amount. The penalty becomes due once "
        "payment is at least one (1) calendar day late.", b))
    st.append(Paragraph("5. Delivery and Acceptance", h))
    st.append(Paragraph("Goods are delivered DAP the Buyer's designated facility. The Buyer has ten (10) days from "
        "delivery to inspect and reject non-conforming goods.", b))
    st.append(Paragraph("6. Term and Termination", h))
    st.append(Paragraph("This Agreement is valid for twenty-four (24) months and renews automatically for successive "
        "twelve-month periods unless either party gives ninety (90) days written notice. Either party may terminate "
        "for material breach that remains uncured thirty (30) days after written notice.", b))
    st.append(Paragraph("7. Confidentiality and Governing Law", h))
    st.append(Paragraph("Each party shall keep the terms of this Agreement confidential. This Agreement is governed "
        "by the laws of the State of New York. Disputes shall be settled by arbitration.", b))
    st.append(Spacer(1, 30))
    sig = Table([["For the Buyer", "For the Supplier"],
                 ["Globex Manufacturing Inc.", s["name"]],
                 ["_______________________", "_______________________"],
                 ["Procurement Director", "Managing Director"]], colWidths=[230, 230])
    st.append(sig)
    doc.build(st)

def make_scan(src, dst):
    tmp = dst.replace(".pdf", "_tmp")
    subprocess.run(["pdftoppm", "-r", "150", "-png", src, tmp], check=True)
    imgs = []
    for f in sorted(glob.glob(tmp + "*.png")):
        im = Image.open(f).convert("L").rotate(random.uniform(-0.8, 0.8), fillcolor=255, expand=False)
        im = im.filter(ImageFilter.GaussianBlur(0.7))
        px = im.load()
        for _ in range(4000):
            px[random.randrange(im.width), random.randrange(im.height)] = random.randint(120, 200)
        imgs.append(im.convert("RGB")); os.remove(f)
    imgs[0].save(dst, save_all=True, append_images=imgs[1:], resolution=150)

random.seed(7)
for s in SUPPLIERS:
    p = os.path.join(OUT, s["file"])
    if s["scan"]:
        build(s, p + ".tmp.pdf"); make_scan(p + ".tmp.pdf", p); os.remove(p + ".tmp.pdf")
    else:
        build(s, p)
    print("created", p)
