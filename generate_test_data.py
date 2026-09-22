"""Generate professional, visually distinct vendor invoices (Platypus tables + styles)."""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)
OUT = Path(__file__).parent / "test_invoices"
W, _H = letter

BLUE = colors.HexColor("#1d4ed8")
SLATE = colors.HexColor("#1e293b")
LIGHT = colors.HexColor("#f1f5f9")
MUTED = colors.HexColor("#64748b")

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, leading=26)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, leading=14, spaceAfter=4)
BODY = ParagraphStyle("Body2", parent=styles["Normal"], fontSize=9, leading=12)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10, textColor=MUTED)


def _doc(name: str) -> SimpleDocTemplate:
    OUT.mkdir(exist_ok=True)
    return SimpleDocTemplate(
        str(OUT / name),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
    )


def _header_bar(accent: colors.Color, vendor: str, address: str, doc_title: str) -> list:
    bar = Table([[""]], colWidths=[W - 1.4 * inch])
    bar.setStyle(
        TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent), ("TOPPADDING", (0, 0), (-1, -1), 5)])
    )
    return [
        bar,
        Spacer(1, 0.12 * inch),
        Paragraph(f"<b>{vendor}</b>", TITLE),
        Paragraph(address, SMALL),
        Spacer(1, 0.08 * inch),
        Paragraph(f"<b>{doc_title}</b>", H2),
    ]


def _meta_table(rows: list[list[str]]) -> Table:
    t = Table(rows, colWidths=[1.7 * inch, 2.6 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def _items_table(
    header: list[str], rows: list[list[str]], total_rows: list[list[str]], accent
) -> Table:
    data = [header, *rows, *total_rows]
    t = Table(data, colWidths=[3.0 * inch, 0.9 * inch, 1.2 * inch, 1.2 * inch])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, len(rows)), [colors.white, LIGHT]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    n = len(data)
    for i in range(len(rows) + 1, n):
        style.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def _footer(note: str) -> list:
    return [Spacer(1, 0.18 * inch), Paragraph(note, SMALL)]


def build_acme_happy() -> None:
    story = _header_bar(
        BLUE,
        "Acme Supplies Ltd",
        "14 Foundry Lane, Austin, TX 78701 · accounts@acme.example",
        "TAX INVOICE",
    )
    story += [
        _meta_table(
            [
                ["Bill To:", "Midwest Retail Co. — AP Department"],
                ["Invoice Number:", "INV-2026-001"],
                ["Invoice Date:", "2026-09-10"],
                ["PO Number:", "PO-1001"],
                ["Payment Terms:", "Net 30"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Description", "Qty", "Unit Price", "Amount"],
            [["Industrial widgets (SKU W-100)", "100", "$46.00", "$4,600.00"]],
            [
                ["", "", "Subtotal:", "$4,600.00"],
                ["", "", "Tax (8.7%):", "$400.00"],
                ["", "", "Grand Total:", "$5,000.00"],
            ],
            BLUE,
        ),
        *_footer(
            "From: Acme Supplies Ltd · Remit to accounts@acme.example · Thank you for your business."
        ),
    ]
    _doc("INV-2026-001_happy.pdf").build(story)
    logger.info("wrote %s", "INV-2026-001_happy.pdf")


def build_acme_duplicate() -> None:
    story = _header_bar(
        BLUE,
        "Acme Supplies Ltd",
        "14 Foundry Lane, Austin, TX 78701 · accounts@acme.example",
        "TAX INVOICE — DUPLICATE REPRINT",
    )
    story += [
        _meta_table(
            [
                ["Bill To:", "Midwest Retail Co. — AP Department"],
                ["Invoice Number:", "INV-2026-001"],
                ["Invoice Date:", "September 14, 2026"],
                ["PO Number:", "PO-1001"],
                ["Payment Terms:", "Net 30"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Description", "Qty", "Unit Price", "Amount"],
            [["Industrial widgets (SKU W-100)", "100", "$46.00", "$4,600.00"]],
            [
                ["", "", "Subtotal:", "$4,600.00"],
                ["", "", "Tax (8.7%):", "$400.00"],
                ["", "", "Grand Total:", "$5,000.00"],
            ],
            BLUE,
        ),
        *_footer(
            "From: Acme Supplies Ltd · This is a reprint of the original invoice. Do not pay twice."
        ),
    ]
    _doc("INV-2026-001_duplicate.pdf").build(story)
    logger.info("wrote %s", "INV-2026-001_duplicate.pdf")


def build_globex(part: str, inv_no: str, date: str, desc: str) -> None:
    story = _header_bar(
        SLATE,
        "GLOBEX SYSTEMS",
        "500 Meridian Ave, Chicago, IL 60601 · billing@globex.example",
        f"COMMERCIAL INVOICE ({part})",
    )
    story += [
        _meta_table(
            [
                ["Client:", "Midwest Retail Co."],
                ["Invoice No.:", inv_no],
                ["Dated:", date],
                ["Reference:", "PO-1002 / Milestone billing"],
                ["Billed By:", "Globex Systems"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Milestone", "Pct", "Base", "Amount"],
            [[desc, "50%", "$12,000.00", "$6,000.00"]],
            [["", "", "Tax:", "$0.00"], ["", "", "Balance Due:", "$6,000.00"]],
            SLATE,
        ),
        *_footer(
            "Billed By: Globex Systems · Wire instructions on file · Questions: billing@globex.example"
        ),
    ]
    mapping = {"Part 1 of 2": "INV-2026-002a_split1.pdf", "Part 2 of 2": "INV-2026-002b_split2.pdf"}
    _doc(mapping[part]).build(story)
    logger.info("wrote %s", mapping[part])


def build_initech() -> None:
    accent = colors.HexColor("#0f766e")
    story = _header_bar(
        accent, "Initech LLC", "88 Congress St, Boston, MA 02110 · hello@initech.example", "INVOICE"
    )
    story += [
        _meta_table(
            [
                ["Bill To:", "Midwest Retail Co."],
                ["Invoice #:", "INV-2026-003"],
                ["Issued:", "September 13, 2026"],
                ["Client PO:", "PO-1003"],
                ["From:", "Initech LLC"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Service", "Basis", "Rate", "Amount"],
            [
                [
                    "Cloud migration — fixed-fee bundle (discovery → cutover)",
                    "Fixed fee",
                    "—",
                    "$2,900.00",
                ]
            ],
            [["", "", "Amount Due:", "$2,900.00"]],
            accent,
        ),
        *_footer(
            "From: Initech LLC · Fixed-fee bundle. Tax included where applicable — no separate tax breakdown."
        ),
    ]
    _doc("INV-2026-003_overtolerance.pdf").build(story)
    logger.info("wrote %s", "INV-2026-003_overtolerance.pdf")


def build_umbrella_statement() -> None:
    accent = colors.HexColor("#7c3aed")
    story = _header_bar(
        accent,
        "Umbrella Corp",
        "1 Hive Plaza, Newark, NJ 07101 · ar@umbrella.example",
        "MONTHLY STATEMENT (NOT AN INVOICE)",
    )
    story += [
        _meta_table(
            [
                ["Account:", "Midwest Retail Co."],
                ["Statement Date:", "15-Sep-2026"],
                ["PO Ref:", "PO-1004"],
                ["From:", "Umbrella Corp"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Activity", "Period", "Rate", "Amount"],
            [["Misc. services — see attached detail", "Aug 2026", "—", "$1,200.00"]],
            [["", "", "Total Payable:", "$1,200.00"]],
            accent,
        ),
        *_footer(
            "From: Umbrella Corp · No invoice number on this statement — request a formal invoice before paying."
        ),
    ]
    _doc("INV-2026-004_missing.pdf").build(story)
    logger.info("wrote %s", "INV-2026-004_missing.pdf")


def build_vandelay_bundled() -> None:
    """Bundled single-line bill, tax embedded, explicit PO. Centered import-house style."""
    accent = colors.HexColor("#c2410c")
    center = ParagraphStyle("Center", parent=BODY, alignment=1)
    title_c = ParagraphStyle("TitleC", parent=TITLE, alignment=1)
    story = [
        Paragraph("<b>VANDELAY IMPORTS</b>", title_c),
        Paragraph("29 Export Row, Jersey City, NJ 07310 · sales@vandelay.example", center),
        Spacer(1, 0.1 * inch),
        Paragraph(
            "<b>SALES INVOICE — bundled lot pricing</b>",
            ParagraphStyle("H2C", parent=H2, alignment=1),
        ),
        Spacer(1, 0.1 * inch),
        _meta_table(
            [
                ["Sold To:", "Midwest Retail Co."],
                ["Invoice No.:", "VND-2026-051"],
                ["Date:", "2026-09-16"],
                ["P.O.:", "PO-1006"],
                ["From:", "Vandelay Imports"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        Paragraph(
            "One lot — assorted latex goods (styles as per packing list PL-881, 400 units total). "
            "Lot price covers freight to dock.",
            BODY,
        ),
        Spacer(1, 0.1 * inch),
        _items_table(
            ["Lot", "Units", "Terms", "Amount"],
            [["PL-881 assorted", "400", "Ex-dock", "$3,200.00"]],
            [["", "", "Total (incl. tax):", "$3,200.00"]],
            accent,
        ),
        *_footer(
            "From: Vandelay Imports · Sales tax is included in the total above. No separate tax due."
        ),
    ]
    _doc("INV-2026-005_bundled.pdf").build(story)
    logger.info("wrote %s", "INV-2026-005_bundled.pdf")


def build_hooli_notax() -> None:
    """Itemised hardware bill with no tax line at all. Right-aligned meta, red minimal style."""
    accent = colors.HexColor("#b91c1c")
    story = _header_bar(
        accent, "Hooli", "1600 Amphitheatre Way, Mountain View, CA · ap@hooli.example", "INVOICE"
    )
    bill = Table(
        [[Paragraph("<b>Bill To:</b> Midwest Retail Co.", BODY)]],
        colWidths=[3.2 * inch],
    )
    meta = _meta_table(
        [
            ["INVOICE #:", "HO-2026-118"],
            ["Date:", "2026-09-16"],
            ["PO:", "PO-1007"],
            ["From:", "Hooli"],
        ]
    )
    top = Table([[bill, meta]], colWidths=[3.2 * inch, 4.3 * inch])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [
        top,
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Hardware", "Qty", "Unit", "Amount"],
            [
                ["HooliBox v3 appliance", "10", "$820.00", "$8,200.00"],
                ["Rack rails + PDU kit", "10", "$90.00", "$900.00"],
            ],
            [["", "", "Total Due:", "$9,100.00"]],
            accent,
        ),
        *_footer("From: Hooli · Equipment sale — no sales tax collected on this order."),
    ]
    _doc("INV-2026-006_notax.pdf").build(story)
    logger.info("wrote %s", "INV-2026-006_notax.pdf")


def build_stark_implied_po() -> None:
    """Premium two-column invoice with NO purchase-order reference (implied-PO case)."""
    accent = colors.HexColor("#0a3161")
    gold = ParagraphStyle("Gold", parent=H2, textColor=colors.HexColor("#b45309"), alignment=1)
    addr = ParagraphStyle("Addr", parent=SMALL, alignment=1)
    two = Table(
        [
            [
                Paragraph("<b>Stark Industries</b><br/>200 Park Ave, New York, NY", BODY),
                Paragraph("<b>Ship To:</b><br/>Midwest Retail Co.<br/>Chicago, IL", BODY),
            ]
        ],
        colWidths=[3.75 * inch, 3.75 * inch],
    )
    story = [
        Paragraph("<b>STARK INDUSTRIES — INVOICE</b>", TITLE),
        Paragraph("200 Park Ave, New York, NY 10166 · payables@stark.example", addr),
        Spacer(1, 0.1 * inch),
        two,
        Spacer(1, 0.1 * inch),
        _meta_table(
            [
                ["Invoice No.:", "2026-SI-0441"],
                ["Date:", "September 17, 2026"],
                ["From:", "Stark Industries"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Component", "Qty", "Unit Price", "Amount"],
            [
                ["Arc-reactor housing Mk II", "20", "$310.00", "$6,200.00"],
                ["Copper busbar set", "20", "$80.00", "$1,600.00"],
            ],
            [["", "", "Amount Payable:", "$7,800.00"]],
            accent,
        ),
        Paragraph("Priority client billing — net 15.", gold),
        *_footer("Questions: payables@stark.example · Reference your internal PO when remitting."),
    ]
    _doc("INV-2026-007_implied.pdf").build(story)
    logger.info("wrote %s", "INV-2026-007_implied.pdf")


def build_wayne_nodate() -> None:
    """Art-deco black/gold invoice with NO date field anywhere."""
    accent = colors.HexColor("#111111")
    story = _header_bar(
        accent,
        "WAYNE ENTERPRISES",
        "1007 Mountain Drive, Gotham, NJ · finance@wayne.example",
        "INVOICE",
    )
    story += [
        _meta_table(
            [
                ["Client:", "Midwest Retail Co."],
                ["Invoice No.:", "WE-6654"],
                ["Purchase Order:", "PO-1008"],
                ["From:", "Wayne Enterprises"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Equipment", "Qty", "Unit", "Amount"],
            [
                ["Grapnel winch assembly", "4", "$950.00", "$3,800.00"],
                ["Kevlar cable 100m", "8", "$100.00", "$800.00"],
            ],
            [["", "", "Grand Total:", "$4,600.00"]],
            accent,
        ),
        *_footer("From: Wayne Enterprises · Payment terms Net 30 from receipt."),
    ]
    _doc("INV-2026-008_nodate.pdf").build(story)
    logger.info("wrote %s", "INV-2026-008_nodate.pdf")


def build_tyrell_unclear_total() -> None:
    """Biotech letter-style bill: paragraph line items, NO total line (unclear total)."""
    accent = colors.HexColor("#4d7c0f")
    story = _header_bar(
        accent,
        "Tyrell Corporation",
        "600 E. Grand Ave, Los Angeles, CA · billing@tyrell.example",
        "INVOICE TY-2026-77",
    )
    story += [
        _meta_table(
            [
                ["Client:", "Midwest Retail Co."],
                ["Invoice No.:", "TY-2026-77"],
                ["Date:", "2026-09-19"],
                ["PO:", "PO-1011"],
                ["From:", "Tyrell Corp"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        Paragraph("Genetic sequencing services, August batch:", BODY),
        Spacer(1, 0.06 * inch),
        Paragraph("— Exome panel, 30 samples at $70.00 per sample: $2,100.00", BODY),
        Paragraph("— Culture media prep, 12 runs at $350.00 per run: $4,200.00", BODY),
        Spacer(1, 0.1 * inch),
        Paragraph(
            "Please remit at your convenience. Detailed statements available on request.", BODY
        ),
        *_footer("From: Tyrell Corp · billing@tyrell.example"),
    ]
    _doc("INV-2026-009_unclear.pdf").build(story)
    logger.info("wrote %s", "INV-2026-009_unclear.pdf")


def build_cyberdyne_close_over() -> None:
    """Slightly over PO tolerance — should Flag, not Reject."""
    accent = colors.HexColor("#991b1b")
    story = _header_bar(
        accent,
        "CYBERDYNE SYSTEMS",
        "18144 El Camino Real, Sunnyvale, CA · ar@cyberdyne.example",
        "INVOICE",
    )
    story += [
        _meta_table(
            [
                ["Bill To:", "Midwest Retail Co."],
                ["Invoice Number:", "CD-2026-309"],
                ["Date:", "09/20/2026"],
                ["P.O. No.:", "PO-1009"],
                ["From:", "Cyberdyne Systems"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Part No.", "Qty", "Price", "Amount"],
            [
                ["CD-SV-200 servo motor", "10", "$480.00", "$4,800.00"],
                ["CD-CT-10 controller", "2", "$300.00", "$600.00"],
            ],
            [
                ["", "", "Subtotal:", "$5,400.00"],
                ["", "", "Sales Tax:", "$220.00"],
                ["", "", "Total:", "$5,620.00"],
            ],
            accent,
        ),
        *_footer("From: Cyberdyne Systems · Freight prepaid. Net 30."),
    ]
    _doc("INV-2026-010_close.pdf").build(story)
    logger.info("wrote %s", "INV-2026-010_close.pdf")


def build_soylent_way_over() -> None:
    """Far over PO — should Reject."""
    accent = colors.HexColor("#15803d")
    story = _header_bar(
        accent, "Soylent Corp", "44 Greenway Blvd, Chicago, IL · billing@soylent.example", "INVOICE"
    )
    story += [
        _meta_table(
            [
                ["Customer:", "Midwest Retail Co."],
                ["Invoice #:", "SOY-2210"],
                ["Date:", "September 21, 2026"],
                ["PO Number:", "PO-1010"],
                ["From:", "Soylent Corp"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Lot", "Cases", "Per Case", "Amount"],
            [
                ["Meal powder v2 (assorted)", "60", "$70.00", "$4,200.00"],
                ["Drink RTD 12-pack", "20", "$35.00", "$700.00"],
            ],
            [["", "", "Total Due:", "$4,900.00"]],
            accent,
        ),
        *_footer("From: Soylent Corp · Perishable — confirm cold-chain on receipt."),
    ]
    _doc("INV-2026-011_wayover.pdf").build(story)
    logger.info("wrote %s", "INV-2026-011_wayover.pdf")


def build_gekko_unknown() -> None:
    """Unknown vendor + unknown PO — should Flag for manual match. Serif pinstripe style."""
    accent = colors.HexColor("#1e3a5f")
    serif = ParagraphStyle("Serif", parent=BODY, fontName="Times-Roman")
    serif_t = ParagraphStyle("SerifT", parent=TITLE, fontName="Times-Bold")
    bar = Table([[""]], colWidths=[W - 1.4 * inch])
    bar.setStyle(
        TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent), ("TOPPADDING", (0, 0), (-1, -1), 3)])
    )
    bar2 = Table([[""]], colWidths=[W - 1.4 * inch])
    bar2.setStyle(
        TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent), ("TOPPADDING", (0, 0), (-1, -1), 1)])
    )
    story = [
        bar,
        bar2,
        Spacer(1, 0.1 * inch),
        Paragraph("<b>GEKKO &amp; CO.</b>", serif_t),
        Paragraph("400 Wall Street, New York, NY · settlements@gekko.example", SMALL),
        Spacer(1, 0.08 * inch),
        _meta_table(
            [
                ["Client:", "Midwest Retail Co."],
                ["Invoice No.:", "GK-8801"],
                ["Date:", "2026-09-22"],
                ["Re:", "PO-9999 (per phone order)"],
                ["From:", "Gekko & Co."],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Block", "Shares", "Price", "Amount"],
            [["Blue-chip block trade settlement", "100", "$70.00", "$7,000.00"]],
            [["", "", "Commission:", "$700.00"], ["", "", "Grand Total:", "$7,700.00"]],
            accent,
        ),
        Spacer(1, 0.1 * inch),
        Paragraph("Greed is good — settlement T+2.", serif),
        *_footer("From: Gekko & Co. · settlements@gekko.example"),
    ]
    _doc("INV-2026-012_unknown.pdf").build(story)
    logger.info("wrote %s", "INV-2026-012_unknown.pdf")


def build_massive_scanned() -> None:
    """Simulated flatbed scan: full-page raster image, no text layer (tests OCR fallback)."""
    from PIL import Image, ImageDraw
    from reportlab.platypus import Image as RLImage

    lines = [
        "MASSIVE DYNAMIC  |  744 Beacon St, Boston, MA | billing@massive.example",
        "INVOICE — SCANNED COPY",
        "",
        "Bill To: Midwest Retail Co.",
        "Invoice Number: INV-2026-013",
        "Date: 2026-09-23",
        "PO Number: PO-1012",
        "From: Massive Dynamic",
        "",
        "Description: Sensor array calibration service ......... $2,900.00",
        "Tax: $0.00",
        "Total: $2,900.00",
    ]
    img = Image.new("RGB", (1650, 2100), "white")
    d = ImageDraw.Draw(img)
    y = 120
    for line in lines:
        d.text((120, y), line, fill="black")
        y += 64
    scan_path = OUT / "_scan_tmp.png"
    OUT.mkdir(exist_ok=True)
    img.save(scan_path)
    story = [RLImage(str(scan_path), width=7.0 * inch, height=8.97 * inch)]
    _doc("INV-2026-013_scanned.pdf").build(story)
    scan_path.unlink(missing_ok=True)
    logger.info("wrote %s", "INV-2026-013_scanned.pdf")


def build_globex_email_correction() -> None:
    """Email-printout style correction notice billing far over the PO (should Reject)."""
    mono = ParagraphStyle("Mono", parent=BODY, fontName="Courier", fontSize=9, leading=12)
    story = [
        Paragraph(
            "<b>From:</b> billing@globex.example<br/><b>Subject:</b> Corrected final invoice — PO-1002",
            mono,
        ),
        Spacer(1, 0.1 * inch),
        Paragraph("------------------------------------------------------------", mono),
        Paragraph("GLOBEX SYSTEMS — CORRECTED FINAL INVOICE", mono),
        Paragraph("Invoice No. INV-2026-002C", mono),
        Paragraph("Date: 09/24/2026", mono),
        Paragraph("Billed By: Globex Systems", mono),
        Paragraph("------------------------------------------------------------", mono),
        Paragraph("Team — the two milestone invoices understated scope. This", mono),
        Paragraph("correction supersedes them. We previously billed $6,000.00", mono),
        Paragraph("on 09/11 and $6,000.00 on 09/12.", mono),
        Spacer(1, 0.08 * inch),
        Paragraph("Additional integration work (out of scope): $900.00", mono),
        Paragraph("Corrected total: $12,900.00", mono),
        Paragraph("Reference: PO-1002", mono),
        *_footer("Billed By: Globex Systems · Emailed invoices are valid originals."),
    ]
    _doc("INV-2026-014_splitx.pdf").build(story)
    logger.info("wrote %s", "INV-2026-014_splitx.pdf")


def build_umbrella_closed_numbered() -> None:
    """Numbered invoice against a CLOSED PO (should Reject). Compact compliance style."""
    accent = colors.HexColor("#475569")
    story = _header_bar(
        accent,
        "Umbrella Corp",
        "1 Hive Plaza, Newark, NJ 07101 · ar@umbrella.example",
        "TAX INVOICE",
    )
    story += [
        _meta_table(
            [
                ["Account:", "Midwest Retail Co."],
                ["Invoice No.:", "UMB-2026-310"],
                ["Date:", "2026-09-25"],
                ["PO:", "PO-1004"],
                ["From:", "Umbrella Corp"],
            ]
        ),
        Spacer(1, 0.15 * inch),
        _items_table(
            ["Service", "Qty", "Rate", "Amount"],
            [["Decontamination service, Lab 7", "3", "$300.00", "$900.00"]],
            [["", "", "Grand Total:", "$900.00"]],
            accent,
        ),
        *_footer("From: Umbrella Corp · Quote Q-77 applies."),
    ]
    _doc("INV-2026-015_closed.pdf").build(story)
    logger.info("wrote %s", "INV-2026-015_closed.pdf")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_acme_happy()
    build_acme_duplicate()
    build_globex("Part 1 of 2", "INV-2026-002A", "09/11/2026", "Phase 1 delivery — implementation")
    build_globex("Part 2 of 2", "INV-2026-002B", "09/12/2026", "Phase 2 delivery — go-live")
    build_initech()
    build_umbrella_statement()
    build_vandelay_bundled()
    build_hooli_notax()
    build_stark_implied_po()
    build_wayne_nodate()
    build_tyrell_unclear_total()
    build_cyberdyne_close_over()
    build_soylent_way_over()
    build_gekko_unknown()
    build_massive_scanned()
    build_globex_email_correction()
    build_umbrella_closed_numbered()


if __name__ == "__main__":
    main()
