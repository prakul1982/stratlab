"""Tax invoices for subscription payments, under India's GST rules, one per payment.

- The seller's details (legal name, address, state, GSTIN, LUT ARN) are set in Admin → Invoices.
- Plan prices include GST. In India the 18% is split CGST 9% + SGST 9% when the buyer is in the seller's state (or
  hasn't given a state: the seller's location is then the place of supply), and IGST 18% otherwise.
- A buyer outside India (a card issued abroad, or a billing country other than India) is an export of services:
  zero-rated under a Letter of Undertaking when an LUT ARN is set, otherwise IGST 18% is shown as included.
- A seller without a GSTIN issues a plain invoice that says it isn't registered under GST.
- Numbers run in one series per Indian financial year: SL/2026-27/0001.
Not tax advice: the rules above are the standard ones; the owner's accountant should confirm them."""
import base64
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

from . import db

SELLER = "invoice:seller"
IST = timezone(timedelta(hours=5, minutes=30))
_lock = threading.Lock()

STATES = {  # GST state codes
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
SAC = "998431"     # online information and database access or retrieval services
FIELDS = ("legal_name", "address", "state", "gstin", "pan", "lut_arn", "email", "prefix")


def _get(key: str, default=None):
    try:
        raw = db.get_setting(key)
        return json.loads(raw) if raw else default
    except Exception:
        return default


def seller() -> dict:
    s = _get(SELLER, {}) or {}
    return {f: (s.get(f) or "") for f in FIELDS} | {"prefix": s.get("prefix") or "SL"}


def save_seller(data: dict) -> dict:
    import re
    out = {f: str(data.get(f) or "").strip()[:400] for f in FIELDS}
    out["gstin"] = out["gstin"].upper()
    if out["gstin"] and not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", out["gstin"]):
        raise ValueError("That GSTIN doesn't look right: 15 characters, like 27ABCDE1234F1Z5.")
    if out["state"] and out["state"] not in STATES:
        raise ValueError("Pick the state from the list.")
    if out["gstin"] and out["state"] and out["gstin"][:2] != out["state"]:
        raise ValueError(f"The GSTIN starts with {out['gstin'][:2]}, which is {STATES.get(out['gstin'][:2], 'another state')}, not the state chosen.")
    out["prefix"] = re.sub(r"[^A-Z0-9]", "", out["prefix"].upper())[:6] or "SL"
    db.set_setting(SELLER, json.dumps(out))
    return seller()


def fy(d: datetime) -> str:
    """The Indian financial year of a date, as on invoices: 2026-27."""
    d = d.astimezone(IST)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def tax_lines(total: float, s: dict, buyer: dict) -> tuple[list[dict], str, str]:
    """(tax lines, the kind of supply, the note printed on the invoice) for a tax-inclusive total."""
    export = buyer.get("country", "IN") != "IN"
    if not s.get("gstin"):
        return [], "Unregistered", "The supplier is not registered under GST, so no GST is charged."
    if export and s.get("lut_arn"):
        return ([{"name": "IGST 0%", "rate": 0, "amount": 0.0}], "Export (zero-rated)",
                f"Supply meant for export under LUT without payment of IGST (LUT ARN {s['lut_arn']}).")
    taxable = round(total / 1.18, 2)
    gst = round(total - taxable, 2)
    if export or (buyer.get("state") and buyer["state"] != s.get("state")):
        return ([{"name": "IGST 18%", "rate": 18, "amount": gst}], "Export (IGST paid)" if export else "Inter-state",
                "IGST included in the price." if not export else "Export of services with payment of IGST (included in the price).")
    half = round(gst / 2, 2)
    return ([{"name": "CGST 9%", "rate": 9, "amount": half}, {"name": "SGST 9%", "rate": 9, "amount": round(gst - half, 2)}],
            "Intra-state", "GST included in the price.")


def make(payment: dict, user: dict, plan: str, period: str) -> dict:
    """The invoice for one payment, created once (a second call for the same payment returns the first)."""
    pid = payment["id"]
    with _lock:
        existing = _get(f"invoice-of:{pid}")
        if existing:
            return _get(f"invoice:{existing}")
        s = seller()
        at = datetime.fromtimestamp(int(payment.get("created_at") or datetime.now(timezone.utc).timestamp()), timezone.utc)
        year = fy(at)
        counter_key = f"invoice:counter:{year}"
        n = int(_get(counter_key, 0) or 0) + 1
        number = f"{s['prefix']}/{year}/{n:04d}"
        billing = _get(f"billing:{user['id']}", {}) or {}
        country = billing.get("country") or ("XX" if payment.get("international") else "IN")
        buyer = {"name": billing.get("name") or user.get("email") or "", "email": user.get("email") or payment.get("email") or "",
                 "address": billing.get("address") or "", "state": billing.get("state") or "", "country": country,
                 "gstin": billing.get("gstin") or ""}
        currency = payment.get("currency") or "INR"
        total = round((payment.get("amount") or 0) / 100, 2)
        lines, supply, note = tax_lines(total, s, buyer)
        tax = round(sum(x["amount"] for x in lines), 2)
        inv = {"number": number, "fy": year, "date": at.astimezone(IST).date().isoformat(), "payment_id": pid,
               "user_id": user["id"], "seller": s, "buyer": buyer, "supply": supply, "note": note, "currency": currency,
               "item": {"description": f"StratLab {plan.title()} plan, {'yearly' if period == 'year' else 'monthly'} subscription",
                        "sac": SAC, "taxable": round(total - tax, 2)},
               "taxes": lines, "total": total,
               "place_of_supply": "Outside India" if country != "IN" else STATES.get(buyer["state"] or s.get("state"), "India")}
        db.set_setting(counter_key, json.dumps(n))
        db.set_setting(f"invoice:{number}", json.dumps(inv))
        db.set_setting(f"invoice-of:{pid}", json.dumps(number))
        mine = _get(f"invoices:{user['id']}", []) or []
        db.set_setting(f"invoices:{user['id']}", json.dumps(mine + [number]))
        index = _get(f"invoices:fy:{year}", []) or []
        db.set_setting(f"invoices:fy:{year}", json.dumps(index + [number]))
        return inv


def get(number: str) -> dict | None:
    return _get(f"invoice:{number}")


def of_user(uid: str) -> list[dict]:
    return [i for i in (get(n) for n in reversed(_get(f"invoices:{uid}", []) or [])) if i]


def of_year(year: str) -> list[dict]:
    return [i for i in (get(n) for n in _get(f"invoices:fy:{year}", []) or []) if i]


def save_billing(uid: str, data: dict) -> dict:
    """The buyer's billing details for future invoices (name, address, state, GSTIN for a business, country)."""
    import re
    out = {k: str(data.get(k) or "").strip()[:300] for k in ("name", "address", "state", "gstin", "country")}
    out["country"] = (out["country"] or "IN").upper()[:2]
    out["gstin"] = out["gstin"].upper()
    if out["gstin"] and not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", out["gstin"]):
        raise ValueError("That GSTIN doesn't look right: 15 characters, like 27ABCDE1234F1Z5.")
    if out["country"] == "IN" and out["state"] and out["state"] not in STATES:
        raise ValueError("Pick your state from the list.")
    if out["country"] != "IN":
        out["state"] = ""
    db.set_setting(f"billing:{uid}", json.dumps(out))
    return out


def billing_of(uid: str) -> dict:
    return _get(f"billing:{uid}", {}) or {}


PRINT_JS = 'document.getElementById("print").onclick=function(){print()};'
PRINT_HASH = base64.b64encode(hashlib.sha256(PRINT_JS.encode()).digest()).decode()
CSP = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{PRINT_HASH}'"


def html(inv: dict) -> str:
    """The invoice as a printable page (the browser's Print → Save as PDF gives the PDF)."""
    from html import escape as e
    s, b = inv["seller"], inv["buyer"]
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(inv["currency"], inv["currency"] + " ")
    money = lambda v: f"{sym}{v:,.2f}"  # noqa: E731
    title = "Tax invoice" if s.get("gstin") else "Invoice"
    rows = "".join(f"<tr><td>{e(t['name'])}</td><td class=n>{money(t['amount'])}</td></tr>" for t in inv["taxes"])
    # opened under the site's own origin: no script may run but the print button's own (a second guard after escaping)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{e(title)} {e(inv['number'])}</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;color:#1d1b17;max-width:760px;margin:32px auto;padding:0 16px}}
h1{{font-size:22px;margin:0 0 4px}}table{{width:100%;border-collapse:collapse;margin:12px 0}}td,th{{padding:6px 8px;border-bottom:1px solid #ddd;text-align:left}}
.n{{text-align:right}}.cols{{display:flex;gap:32px;flex-wrap:wrap}}.cols div{{flex:1;min-width:240px}}small{{color:#666}}
@media print{{button{{display:none}}}}</style></head><body>
<button id="print">Print or save as PDF</button><script>{PRINT_JS}</script>
<h1>{e(title)}</h1><div>No. <b>{e(inv['number'])}</b> · Date {e(inv['date'])} · Payment {e(inv['payment_id'])}</div>
<div class=cols><div><h3>From</h3><b>{e(s.get('legal_name') or 'StratLab')}</b><br>{e(s.get('address') or '')}<br>
{('State: ' + e(STATES.get(s.get('state'), '')) + ' (' + e(s.get('state')) + ')<br>') if s.get('state') else ''}
{('GSTIN: ' + e(s['gstin']) + '<br>') if s.get('gstin') else ''}{('PAN: ' + e(s['pan']) + '<br>') if s.get('pan') else ''}{e(s.get('email') or '')}</div>
<div><h3>To</h3><b>{e(b.get('name') or '')}</b><br>{e(b.get('address') or '')}<br>{e(b.get('email') or '')}<br>
{('GSTIN: ' + e(b['gstin']) + '<br>') if b.get('gstin') else ''}Place of supply: {e(inv['place_of_supply'])}</div></div>
<table><tr><th>Description</th><th>SAC</th><th class=n>Taxable value</th></tr>
<tr><td>{e(inv['item']['description'])}</td><td>{e(inv['item']['sac'])}</td><td class=n>{money(inv['item']['taxable'])}</td></tr></table>
<table>{rows}<tr><th>Total ({e(inv['currency'])})</th><th class=n>{money(inv['total'])}</th></tr></table>
<p><small>{e(inv['note'])} Supply: {e(inv['supply'])}.</small></p></body></html>"""
