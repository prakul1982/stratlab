"""Synthetic NSDL-style consolidated account statements for tests: the layout casparser reads (a cover page, a summary page
with the demat account roster, then each account's holdings table), with a made-up investor, made-up companies and made-up
numbers, encrypted with a password. Never a real statement."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas


def make_nsdl(password: str, accounts: list[dict], period=("01-Sep-2026", "30-Sep-2026"), name="TEST INVESTOR",
              pan="ABCDE1234F", footer: str = "", depository: str = "NSDL") -> bytes:
    """accounts: [{"broker", "dp_id", "client_id", "equities": [(isin, ticker, company, shares, price)]}]."""
    buf = io.BytesIO()
    enc = StandardEncryption(password, ownerPassword=password + "-owner", canPrint=1, strength=128)
    c = canvas.Canvas(buf, pagesize=A4, encrypt=enc)
    _, h = A4

    def text(x, y, s, size=8, right=False):
        c.setFont("Helvetica", size)
        (c.drawRightString if right else c.drawString)(x, y, s)

    # page 1: the cover
    if depository == "CDSL":
        text(40, h - 40, "Central Depository Services (India) Limited", 9)
        text(40, h - 60, "Consolidated Account Statement", 14)
    else:
        text(40, h - 60, "NSDL Consolidated Account Statement", 14)
    text(40, h - 80, f"Statement for the period from {period[0]} to {period[1]}", 9)
    text(40, h - 100, "Test Street 1, Testville 400001", 8)
    c.showPage()
    # page 2: the summary of accounts
    text(40, h - 30, "CAS ID: 00000001" if depository == "CDSL" else "NSDL ID: 00000001", 8)
    text(40, h - 40, name, 8)
    text(40, h - 50, "1 Example Street", 8)
    text(40, h - 60, "PINCODE: 400001", 8)
    y = h - 100
    text(40, y, "ACCOUNT SUMMARY", 10)
    y -= 20
    text(40, y, "Your Consolidated Account Statement is in the single name of", 8)
    y -= 14
    text(40, y, f"{name} (PAN:{pan})", 8)
    y -= 24
    text(40, y, "Account Type", 8)
    text(200, y, "Account Details", 8)
    text(400, y, "No. of ISINs", 8)
    text(480, y, "Value in INR", 8)
    y -= 16
    for a in accounts:
        text(40, y, f"{depository} Demat Account", 8)
        text(130, y, a["broker"], 8)
        text(250, y, f"DP ID:{a['dp_id']} Client ID:{a['client_id']}", 8)
        text(400, y, str(len(a["equities"])), 8)
        text(480, y, f"{sum(e[3] * e[4] for e in a['equities']):,.2f}", 8)
        y -= 34
    c.showPage()
    # then one page per account
    for a in accounts:
        y = h - 60
        text(40, y, f"{depository} Demat Account", 9)
        text(150, y, a["broker"], 9)
        text(300, y, f"DP ID:{a['dp_id']} Client ID:{a['client_id']}", 8)
        text(450, y, "ACCOUNT HOLDER", 8)
        text(520, y, f"{name} (PAN:{pan})", 8)
        y -= 24
        text(40, y, "Equity Shares", 9)
        y -= 18
        text(40, y, "Stock Symbol", 8)
        text(130, y, "Company Name", 8)
        text(330, y, "Face Value", 8)
        text(390, y, "No. of Shares", 8)
        text(460, y, "Market Price", 8)
        text(530, y, "Value in INR", 8)
        y -= 16
        for isin, ticker, company, shares, price in a["equities"]:
            text(40, y, isin, 8)
            text(40, y - 9, ticker, 8)
            text(130, y, company, 8)
            text(330, y, "1.00", 8)
            text(390, y, f"{shares:,.3f}".rstrip("0").rstrip("."), 8)
            text(460, y, f"{price:,.2f}", 8)
            text(530, y, f"{shares * price:,.2f}", 8)
            y -= 24
        text(40, y, "Sub Total", 8)
        text(530, y, f"{sum(e[3] * e[4] for e in a['equities']):,.2f}", 8)
        c.showPage()
    if footer:
        text(40, h - 60, footer, 8)
        c.showPage()
    c.save()
    return buf.getvalue()
