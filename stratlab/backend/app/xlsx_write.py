"""A small Excel workbook (.xlsx) writer: named sheets of rows, numbers kept as numbers, a bold first row and
column widths, with no spreadsheet library. Text goes in as inline strings; a cell that starts like a formula stays
text, since a workbook never holds formulas here."""
import io
import math
import re
import zipfile
from typing import NamedTuple
from xml.sax.saxutils import escape

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
STYLES = (HEAD + f'<styleSheet {NS.split(" xmlns:r")[0]}><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
          '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill>'
          '<fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders>'
          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
          '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
          '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
          '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
          # the named "Normal" style: without it Excel readers warn "Workbook contains no default style" (DH-013)
          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class Num(NamedTuple):
    """A number with a format of its own (a row of mixed units: a multiple beside percentages)."""
    value: float | None
    fmt: str


def ref(row: int, col: int) -> str:
    s, c = "", col + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return f"{s}{row + 1}"


def sheet_name(name: str, used: set[str]) -> str:
    """Excel's rules: 31 characters at most, none of []:*?/\\, and unique in the workbook."""
    base = re.sub(r"[\[\]:*?/\\]", "-", name).strip()[:31] or "Sheet"
    out, n = base, 2
    while out.lower() in used:
        out = f"{base[:28]} {n}"
        n += 1
    used.add(out.lower())
    return out


def styles(codes: list[str]) -> str:
    """STYLES with a number format of its own for each code (style 3 onwards, in order): a column's format (`workbook` fmts)."""
    if not codes:
        return STYLES
    fmts = f'<numFmts count="{len(codes)}">' + "".join(f'<numFmt numFmtId="{164 + i}" formatCode="{escape(c, {chr(34): "&quot;"})}"/>'
                                                       for i, c in enumerate(codes)) + "</numFmts>"
    xfs = "".join(f'<xf numFmtId="{164 + i}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' for i in range(len(codes)))
    return (STYLES.replace("<fonts ", fmts + "<fonts ", 1).replace('<cellXfs count="3">', f'<cellXfs count="{3 + len(codes)}">', 1)
            .replace("</cellXfs>", xfs + "</cellXfs>", 1))


def _cell(r: int, c: int, v, bold: bool, fmt: int | None = None, own: dict | None = None) -> str:
    if isinstance(v, Num):                     # `own`: each format code's style in this workbook
        v, fmt = v.value, (own or {}).get(v.fmt, fmt)
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        v = "Yes" if v else "No"
    if isinstance(v, (int, float)):
        if not math.isfinite(v):
            return ""
        style = ' s="1"' if bold else (f' s="{fmt}"' if fmt is not None else ' s="2"' if isinstance(v, float) and not v.is_integer() else "")
        return f'<c r="{ref(r, c)}"{style}><v>{v!r}</v></c>' if isinstance(v, float) else f'<c r="{ref(r, c)}"{style}><v>{v}</v></c>'
    text = escape(_BAD.sub("", str(v)))[:32000]
    style = ' s="1"' if bold else ""
    return f'<c r="{ref(r, c)}" t="inlineStr"{style}><is><t xml:space="preserve">{text}</t></is></c>'


def workbook(sheets: list[tuple]) -> bytes:
    """An .xlsx of (name, rows, the row numbers to make bold) sheets; a sheet may add a fourth part, {column: number format code}, for
    the numbers of its rows not made bold (e.g. "0.0%", a date's "d mmm yyyy"); text cells keep no format."""
    used: set[str] = set()
    names = [sheet_name(s[0], used) for s in sheets]
    codes = list(dict.fromkeys([f for s in sheets if len(s) > 3 and s[3] for f in s[3].values()]
                               + [v.fmt for s in sheets for row in s[1] for v in row if isinstance(v, Num)]))
    own = {c: 3 + i for i, c in enumerate(codes)}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels", HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", HEAD + f'<workbook {NS}><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                             for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", styles(codes))
        for i, s in enumerate(sheets):
            rows, bold = s[1], s[2]
            fmt = {c: 3 + codes.index(f) for c, f in (s[3] if len(s) > 3 and s[3] else {}).items()}
            widths: dict[int, int] = {}
            body = []
            for r, row in enumerate(rows):
                cells = []
                for c, v in enumerate(row):
                    cells.append(_cell(r, c, v, r in (bold or set()), fmt.get(c), own))
                    if isinstance(v, Num):
                        v = v.value
                    if v not in (None, ""):
                        widths[c] = max(widths.get(c, 8), min(60, len(str(v)) + 2))
                body.append(f'<row r="{r + 1}">{"".join(cells)}</row>')
            cols = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>' for c, w in sorted(widths.items()))
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", HEAD + f'<worksheet {NS}>' + (f"<cols>{cols}</cols>" if cols else "")
                       + f'<sheetData>{"".join(body)}</sheetData></worksheet>')
    return out.getvalue()
