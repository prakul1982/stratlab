"""Synthetic CDSL-style consolidated account statements for tests (its own layout: the DP and client ids inside the summary
cell, a "HOLDING STATEMENT" table with the balance columns), with a made-up investor, companies and numbers. Never a real one."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas


def make_cdsl(password: str, accounts: list[dict], period=("01-Sep-2026", "30-Sep-2026"), name="TEST INVESTOR",
              pan="ABCDE1234F", as_on="30-09-2026") -> bytes:
    """accounts: [{"broker", "dp_id", "client_id", "equities": [(isin, company, shares, price)]}]."""
    buf = io.BytesIO()
    enc = StandardEncryption(password, ownerPassword=password + "-owner", canPrint=1, strength=128)
    c = canvas.Canvas(buf, pagesize=A4, encrypt=enc)
    _, h = A4

    def text(x, y, s, size=8):
        c.setFont("Helvetica", size)
        c.drawString(x, y, s)

    text(40, h - 40, "Central Depository Services (India) Limited", 9)
    text(40, h - 60, "Consolidated Account Statement", 14)
    text(40, h - 80, f"Statement for the period from {period[0]} to {period[1]}", 9)
    c.showPage()
    text(40, h - 30, "CAS ID: 00000001", 8)
    text(40, h - 40, name, 8)
    text(40, h - 50, "1 Example Street", 8)
    text(40, h - 60, "PINCODE: 400001", 8)
    y = h - 100
    text(40, y, "Your Consolidated Account Statement is in the single name of", 8)
    y -= 14
    text(40, y, f"{name} (PAN:{pan})", 8)
    y -= 24
    for a in accounts:
        text(40, y, "CDSL Demat Account", 8)
        text(150, y, a["broker"], 8)
        text(150, y - 8, f"DP Id: {a['dp_id']} Client Id : {a['client_id']}", 8)
        text(400, y, str(len(a["equities"])), 8)
        text(480, y, f"{sum(e[2] * e[3] for e in a['equities']):,.2f}", 8)
        y -= 34
    c.showPage()
    for a in accounts:
        y = h - 60
        text(40, y, f"DP Name : {a['broker']}  DP ID : {a['dp_id']}  CLIENT ID : {a['client_id']}", 8)
        y -= 20
        text(40, y, f"HOLDING STATEMENT AS ON {as_on}", 9)
        y -= 18
        for x, t in ((40, "ISIN"), (110, "Security"), (270, "Current Bal"), (320, "Frozen Bal"), (365, "Pledge Bal"),
                     (410, "Pledge Setup Bal"), (470, "Free Bal"), (505, "Market Price"), (550, "Value")):
            text(x, y, t, 7)
        y -= 16
        for isin, company, shares, price in a["equities"]:
            qty = f"{shares:,.3f}".rstrip("0").rstrip(".")
            for x, t in ((40, isin), (110, company), (270, qty), (320, "--"), (365, "--"), (410, "--"), (470, qty),
                         (505, f"{price:,.2f}"), (550, f"{shares * price:,.2f}")):
                text(x, y, t)
            y -= 16
        text(40, y, "Sub Total", 8)
        c.showPage()
    c.save()
    return buf.getvalue()
