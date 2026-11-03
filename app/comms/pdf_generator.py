"""
comms/pdf_generator.py
----------------------
Generates official Yards & Parts Automotive Quote PDFs matching the clean corporate quote format:
  - Yards & Parts header (top-left) + date (top-right)
  - Centered quote header
  - 2-column metadata table (Customer, Created, Expires, Sub-total, Coupon code, Total)
  - Itemized parts table with OEM #, QTY, and pricing (with strikethrough & savings if discounted)
  - Personalized customer note + working "Click Here" payment/checkout link
  - Official boxed Terms and Conditions table
"""

import os
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from pathlib import Path


def create_quote_pdf_for_lead(lead_dict: dict, is_discount_offer: bool = False, discount_pct: float = 4.0) -> str:
    """Helper that generates Quote_Detail.pdf in temp_quotes directory and returns its path."""
    lead_id = lead_dict.get("id", "temp")
    temp_dir = Path("temp_quotes")
    temp_dir.mkdir(exist_ok=True)
    pdf_path = str(temp_dir / f"Quote_Detail_{lead_id}_{int(datetime.utcnow().timestamp())}.pdf")
    return generate_quote_pdf(lead_dict, pdf_path, is_discount_offer=is_discount_offer, discount_pct=discount_pct)


def generate_quote_pdf(
    lead_dict: dict,
    output_path: str,
    is_discount_offer: bool = False,
    discount_pct: float = 4.0,
) -> str:
    """
    Builds Quote_Detail.pdf matching the official quote template format.

    Args:
        lead_dict:         Dictionary with customer and part details
        output_path:       Destination file path
        is_discount_offer: True if a 4% commercial discount is applied
        discount_pct:      Discount percentage (default 4.0)

    Returns:
        Absolute path to the created PDF file
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    logo_style = ParagraphStyle(
        'YardsPartsLogo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.white,
        alignment=1,
    )
    date_style = ParagraphStyle(
        'QuoteDate',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#334155'),
        alignment=2,
    )
    title_style = ParagraphStyle(
        'QuoteTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
    )
    meta_label_style = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#0f172a'),
    )
    meta_val_style = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#334155'),
    )
    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
    )
    td_style = ParagraphStyle(
        'TD',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1e293b'),
    )
    td_center = ParagraphStyle(
        'TDCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        alignment=1,
        textColor=colors.HexColor('#1e293b'),
    )
    td_price = ParagraphStyle(
        'TDPrice',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        alignment=2,
        textColor=colors.HexColor('#0f172a'),
    )
    body_style = ParagraphStyle(
        'BodyNote',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
    )
    terms_title = ParagraphStyle(
        'TermsTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0f172a'),
    )
    terms_text = ParagraphStyle(
        'TermsText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155'),
    )

    elements = []

    # ── 1. Top Header (Yards & Parts Header & Date) ───────────────────────────
    now = datetime.utcnow()
    created_str = now.strftime("%b %d, %Y")
    expires_str = (now + timedelta(days=3)).strftime("%b %d, %Y")

    logo_elem = Paragraph("<b>YARDS &amp; PARTS AUTOMOTIVE</b><br/><font size=8 color='#64748B'>B2B Salvage Yard Interchange &amp; Quoting</font>", 
                          ParagraphStyle('LogoFallback', fontName='Helvetica-Bold', fontSize=15, leading=17, textColor=colors.HexColor('#0F172A')))

    header_table = Table([
        [logo_elem, Paragraph(created_str, date_style)]
    ], colWidths=[120, 412])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 14))

    # ── 2. Centered Quote Header ──────────────────────────────────────────────
    elements.append(Paragraph("Service &amp; Parts Official Quote", title_style))
    elements.append(Spacer(1, 14))

    # Calculate pricing
    sub_total = float(lead_dict.get("quote_value_usd", 140.74) or 140.74)
    if is_discount_offer:
        discount_amount = round(sub_total * (discount_pct / 100.0), 2)
        total_price = round(sub_total - discount_amount, 2)
        coupon_str = f"YARDS{int(discount_pct)}"
    else:
        discount_amount = 0.0
        total_price = sub_total
        coupon_str = "STANDARD"

    customer_email = lead_dict.get("email") or "orders@yardsparts.com"
    customer_name = lead_dict.get("customer_name") or "Valued Customer"
    model = lead_dict.get("model") or "Vehicle"
    part_desc = lead_dict.get("part_description") or "Automotive Part Assembly"
    part_number = lead_dict.get("part_number") or "0888580703"
    lead_id = lead_dict.get("id") or 1

    # ── 3. Two-Column Metadata Summary ────────────────────────────────────────
    meta_data = [
        [
            Paragraph("Customer", meta_label_style),
            Paragraph(customer_email, meta_val_style),
            Paragraph("Sub-Total", meta_label_style),
            Paragraph(f"${sub_total:.2f}", td_price),
        ],
        [
            Paragraph("Quote Created", meta_label_style),
            Paragraph(created_str, meta_val_style),
            Paragraph("Coupon code", meta_label_style),
            Paragraph(coupon_str, meta_val_style),
        ],
        [
            Paragraph("Quote Expires", meta_label_style),
            Paragraph(expires_str, meta_val_style),
            Paragraph("Total", meta_label_style),
            Paragraph(f"<b>${total_price:.2f}</b>", td_price),
        ],
    ]

    meta_table = Table(meta_data, colWidths=[90, 200, 100, 142])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    # ── 4. Itemized Parts Table ───────────────────────────────────────────────
    # Parse parts list if multi-part quote, otherwise single item
    parts_list = lead_dict.get("parts")
    if not parts_list and lead_dict.get("items_json"):
        try:
            raw_j = lead_dict["items_json"]
            parts_list = json.loads(raw_j) if isinstance(raw_j, str) else raw_j
        except Exception:
            parts_list = None

    if not parts_list and isinstance(lead_dict.get("items"), list):
        parts_list = lead_dict["items"]

    if not parts_list:
        parts_list = [{
            "part_description": f"{model} {part_desc}",
            "part_number": part_number,
            "price_usd": sub_total,
        }]

    items_rows = [
        [
            Paragraph("Title", th_style),
            Paragraph("Part", th_style),
            Paragraph("QTY", th_style),
            Paragraph("Price", ParagraphStyle('THRight', parent=th_style, alignment=2)),
        ]
    ]

    for p in parts_list:
        p_desc = p.get("part_description") or p.get("partName") or p.get("description") or part_desc
        p_num = p.get("part_number") or p.get("partNumber") or p.get("oemPartNumber") or part_number
        p_price = float(p.get("price_usd") or p.get("sellingPrice") or (sub_total / max(1, len(parts_list))))

        if is_discount_offer:
            p_disc_price = round(p_price * (1.0 - discount_pct / 100.0), 2)
            p_save = round(p_price - p_disc_price, 2)
            price_p = Paragraph(
                f'<font color="#94a3b8"><s>${p_price:.2f}</s></font> '
                f'<font color="#16a34a"><b>${p_disc_price:.2f}</b></font><br/>'
                f'<font color="#16a34a" size="7.5">Save ${p_save:.2f}</font>',
                td_price
            )
        else:
            price_p = Paragraph(f"<b>${p_price:.2f}</b>", td_price)

        items_rows.append([
            Paragraph(f"<b>{p_desc}</b><br/><font size='7.5' color='#64748b'>Certified OEM Inspection Certificate Included</font>", td_style),
            Paragraph(p_num, td_center),
            Paragraph("1", td_center),
            price_p,
        ])

    if len(parts_list) > 1:
        items_rows.append([
            Paragraph("<b>Total Parts Subtotal:</b>", td_style),
            Paragraph(f"<b>{len(parts_list)} Items</b>", td_center),
            Paragraph(str(len(parts_list)), td_center),
            Paragraph(f"<b>${sub_total:.2f}</b>", td_price),
        ])

    items_table = Table(items_rows, colWidths=[272, 100, 50, 110])
    items_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 14))

    # ── 5. Personalized Message & Working "Click Here" Checkout Button ────────
    checkout_url = "https://yardsparts.com/"

    elements.append(Paragraph(f"Dear <b>{customer_name}</b>,", body_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "Thank you for choosing Yards &amp; Parts Automotive. We are trusted by automotive professionals "
        "nationwide to deliver verified Hollander interchange components and dedicated fitment support. You are in good hands!",
        body_style
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "Please review the quote above and go online to complete payment for these parts. "
        "You may click the link below to proceed:",
        body_style
    ))
    elements.append(Spacer(1, 6))

    # Click Here Button / Link (styled as a clickable blue pill link in the PDF)
    elements.append(Paragraph(
        f'<font color="#2563eb" size="11"><b><u><link href="{checkout_url}">Click Here</link></u></b></font>',
        body_style
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Thank You!!", ParagraphStyle('ThankYou', parent=body_style, fontName='Helvetica-Bold')))
    elements.append(Spacer(1, 12))

    # ── 6. Terms and Conditions (Clean Boxed Table Matching PDF) ──────────────
    elements.append(Paragraph("Quote Terms and condition:", terms_title))
    elements.append(Spacer(1, 5))

    terms_data = [
        [Paragraph("<b>Quotation Validity:</b> This quotation remains valid for three (3) days from the date issued.", terms_text)],
        [Paragraph("<b>Invoice:</b> Once issued, invoices are final and non-editable. Customers must provide accurate GST/Tax details at payment. Invoices are available for download from the order confirmation email.", terms_text)],
        [Paragraph("<b>Delivery Timeline:</b> Parts will be delivered within 3 to 8 business days from order confirmation, subject to location and logistics.", terms_text)],
        [Paragraph("<b>Price Revisions:</b> Quoted prices are subject to change due to foreign exchange fluctuations if not accepted within the validity period.", terms_text)],
        [Paragraph("<b>Warranty:</b> Functional defects are covered under a 90-day mechanical warranty and 30-day direct fitment warranty from the invoice date. Cosmetic damages and physical damages are excluded.", terms_text)],
        [Paragraph("<b>Order Confirmation and Refunds:</b> All confirmed orders are processed for warehouse dispatch. Cancellation or refund requests will be reviewed in accordance with policy.", terms_text)],
    ]

    terms_table = Table(terms_data, colWidths=[532])
    terms_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#94a3b8')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
    ]))
    elements.append(terms_table)

    # Build the document
    doc.build(elements)
    return output_path
