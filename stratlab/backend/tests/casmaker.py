"""Synthetic CAMS-style detailed CAS PDFs for tests: the layout the real statement uses (investor block, AMC heading,
folio line, scheme header, the six-column transaction table, the closing balance line), with a made-up investor, made-up
funds and made-up numbers, encrypted with a password. Never a real statement."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

# left edges of Date and Transaction, right edges of the numeric columns
X_DATE, X_TXN, X_AMT, X_UNITS, X_PRICE, X_BAL = 40, 105, 370, 440, 500, 565


def make_cas(password: str, folios: list[dict], period=("01-Jan-2017", "30-Sep-2026"), name="TEST INVESTOR") -> bytes:
    """folios: [{"amc", "folio", "schemes": [{"code", "name", "isin", "rows": [(date, description, amount, units,
    price, balance)], "close", "nav", "nav_date", "cost", "value"}]}]. An empty string leaves a cell blank."""
    buf = io.BytesIO()
    enc = StandardEncryption(password, ownerPassword=password + "-owner", canPrint=1, strength=128)
    c = canvas.Canvas(buf, pagesize=A4, encrypt=enc)
    _, h = A4
    y = [h - 40]

    def text(x, s, size=8, right=False):
        c.setFont("Helvetica", size)
        (c.drawRightString if right else c.drawString)(x, y[0], s)

    def header():
        text(X_DATE, "Date")
        text(X_TXN, "Transaction")
        text(X_AMT, "Amount", right=True)
        text(X_UNITS, "Units", right=True)
        text(X_PRICE, "Price", right=True)
        text(X_BAL, "Unit", right=True)
        y[0] -= 9
        text(X_AMT, "(INR)", right=True)
        text(X_PRICE, "(INR)", right=True)
        text(X_BAL, "Balance", right=True)
        y[0] -= 14

    def down(n=12):
        y[0] -= n
        if y[0] < 60:
            c.showPage()
            y[0] = h - 40
            header()

    text(40, "Email Id: test@example.com")
    text(330, "Consolidated Account Statement", 10)
    down()
    text(40, name)
    text(330, f"{period[0]} To {period[1]}")
    down()
    text(40, "1 Example Street")
    text(330, "CAMSCASWS-000000000-1", 6)
    down()
    text(40, "Testville 400001")
    down()
    text(40, "Mobile: +910000000000")
    down(20)
    header()
    for f in folios:
        text(40, f["amc"])
        down()
        text(40, f"Folio No: {f['folio']}   PAN: AAAAA0000A   KYC: OK  PAN: OK")
        down()
        text(40, name)
        down()
        for s in f["schemes"]:
            text(40, f"{s['code']}-{s['name']} - ISIN: {s['isin']}(Advisor: DIRECT) Registrar : CAMS")
            down()
            text(40, f"Opening Unit Balance: {s.get('open', '0.000')}")
            down()
            for d, desc, amt, units, price, bal in s["rows"]:
                text(X_DATE, d)
                text(X_TXN, desc)
                for x, v in ((X_AMT, amt), (X_UNITS, units), (X_PRICE, price), (X_BAL, bal)):
                    if v != "":
                        text(x, v, right=True)
                down()
            text(40, f"Closing Unit Balance: {s['close']}   NAV on {s['nav_date']}: INR {s['nav']}   "
                     f"Total Cost Value: {s['cost']}   Market Value on {s['nav_date']}: INR {s['value']}", 7)
            down(18)
    c.showPage()
    c.save()
    return buf.getvalue()
