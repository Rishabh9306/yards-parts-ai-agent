"""
comms/email_client.py
---------------------
Sends HTML emails via Gmail SMTP with official Quote_Detail.pdf attachment.
Uses Python's built-in smtplib + email.mime — zero external API keys needed.
"""

import os
import smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST    = "smtp.gmail.com"
SMTP_PORT    = 587
GMAIL_USER   = os.getenv("GMAIL_USER", "")
GMAIL_PASS   = os.getenv("GMAIL_APP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", GMAIL_USER)
SENDER_NAME  = os.getenv("SENDER_NAME", "Yards & Parts Automotive")


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    plain_body: str,
    pdf_attachment_path: str = None,
) -> dict:
    """
    Send an HTML email via Gmail SMTP with optional Quote_Detail.pdf attachment.
    """
    is_placeholder = (
        not GMAIL_USER
        or "your_gmail" in GMAIL_USER
        or not GMAIL_PASS
        or "your_16_character" in GMAIL_PASS
    )

    if is_placeholder:
        print(f"[GMAIL SMTP PREVIEW] To: {to_name} <{to_email}> | Subject: {subject} | Attachment: {pdf_attachment_path}")
        return {
            "status": "simulated",
            "message": f"Email preview generated for {to_email} with Quote_Detail.pdf",
            "message_id": f"sim_{to_email}_{abs(hash(subject)) % 100000}"
        }

    # Outer container: mixed for body + attachments
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]      = f"{to_name} <{to_email}>"

    # Alternative part for plain text & HTML
    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_body,  "html",  "utf-8"))
    msg.attach(alt_part)

    # Attach PDF file if provided
    if pdf_attachment_path and os.path.exists(pdf_attachment_path):
        try:
            with open(pdf_attachment_path, "rb") as f:
                pdf_data = f.read()
                pdf_part = MIMEApplication(pdf_data, _subtype="pdf")
                pdf_filename = "Quote_Detail.pdf"
                pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
                pdf_part.set_param("name", pdf_filename)
                msg.attach(pdf_part)
                print(f"[EMAIL ATTACHMENT] Attached {pdf_filename} ({len(pdf_data)} bytes) for {to_email}")
        except Exception as e:
            print(f"[EMAIL ATTACHMENT WARNING] Could not attach PDF: {e}")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=12) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return {"status": "sent", "message": f"Email delivered to {to_email} with Quote_Detail.pdf", "message_id": f"gmail_{abs(hash(subject)) % 100000}"}
    except Exception as e:
        print(f"[GMAIL SMTP ERROR] Failed to send: {e}")
        return {"status": "failed", "message": str(e), "message_id": ""}


def build_email(lead: dict, touch_number: int, battlecard_text: str, is_discount_offer: bool = False) -> tuple:
    """
    Build subject + HTML + plain-text email matching the official quote format.
    Explicitly states that for detailed code/quote to view Quote_Detail.pdf.
    """
    name  = lead.get("customer_name", "there")
    model = lead.get("model", "your vehicle")
    part  = lead.get("part_description", "the part you quoted")
    price = lead.get("quote_value_usd") or 0.0
    discount_price = round(price * 0.96, 2)
    discount_savings = round(price * 0.04, 2)
    lead_id = lead.get("id", 1)
    checkout_url = "https://yardsparts.com/"

    is_es = lead.get("preferred_language") == "es"

    if is_es:
        if is_discount_offer or touch_number >= 3:
            subject = f"Descuento Comercial Exclusivo del 4% Aprobado: {model} {part} — Repuestos Originales"
            intro = (
                f"Estimado/a {name},<br><br>"
                f"Dando seguimiento a su cotización pendiente para el <strong>{part}</strong> de su <strong>{model}</strong>.<br><br>"
                f"Para ayudarle a tener su vehículo listo lo antes posible, nuestro gerente de despacho autorizó un <strong>descuento comercial exclusivo del 4%</strong> en su orden.<br><br>"
                f"Su precio garantizado ha sido reducido de <s>${price:.2f}</s> a <strong>${discount_price:.2f} USD</strong> "
                f"(ahorrando ${discount_savings:.2f}), con <strong>envío prioritario express gratuito</strong> y rastreo en vivo incluido."
            )
        elif touch_number == 2:
            subject = f"Consulta sobre su cotización de {part} (${price:.2f}) — Repuestos Originales"
            intro = (
                f"Estimado/a {name},<br><br>"
                f"Le escribimos para verificar si su taller o mecánico tiene alguna consulta sobre la compatibilidad OEM o las especificaciones del <strong>{part}</strong> para su {model}."
            )
        else:
            subject = f"Su cotización de {model} {part} está lista — Repuestos Originales"
            intro = (
                f"Estimado/a {name},<br><br>"
                f"Su cotización para el repuesto <strong>{part}</strong> ({model}) está lista con un precio de <strong>${price:.2f} USD</strong> y garantía de ajuste OEM."
            )
        doc_notice_title = "&#128206; Documento Oficial Adjunto (Quote_Detail.pdf):"
        doc_notice_desc = "Para ver el desglose completo, especificaciones OEM y términos de garantía, <b>por favor abra el archivo adjunto en este correo: (<span style='color:#2563eb;font-weight:600;'>Quote_Detail.pdf</span>)</b>."
        btn_text = "Haga Clic Aquí para Completar su Pedido en Línea"
        footer_text = "Gracias por elegir Repuestos Originales. Válido por 3 días a partir de la fecha de emisión.<br>Si tiene preguntas, llame a despacho al <b>+1 (413) 406-2764</b> o responda directamente a este correo."
    else:
        if is_discount_offer or touch_number >= 3:
            subject = f"Special 4% Trade Discount Approved: {model} {part} — Yards & Parts Automotive"
            intro = (
                f"Hi {name},<br><br>"
                f"Following up on your pending quote for the <strong>{part}</strong> for your <strong>{model}</strong>.<br><br>"
                f"Because you've been reviewing this repair and we want to help you get your vehicle back on the road without delay, "
                f"our customer dispatch manager has authorized an <strong>exclusive 4% commercial trade discount</strong> on your order!<br><br>"
                f"Your guaranteed quote has been reduced from <s>${price:.2f}</s> to <strong>${discount_price:.2f} USD</strong> "
                f"(saving you ${discount_savings:.2f}), and we've included <strong>free priority express freight dispatch</strong> with live tracking."
            )
        elif touch_number == 2:
            subject = f"Quick question about your {part} quote (${price:.2f}) — Yards & Parts Automotive"
            intro = (
                f"Hi {name},<br><br>"
                f"Just circling back on your quote for the <strong>{part}</strong> ({model}). "
                f"We know buying replacement automotive components is an important decision, so we wanted to verify whether "
                f"your workshop or technician had any questions on the OEM interchange or fitment specifications."
            )
        else:
            subject = f"Your {model} {part} quote is ready — Yards & Parts Automotive"
            intro = (
                f"Hi {name},<br><br>"
                f"You recently requested a quote for <strong>{part}</strong> for your <strong>{model}</strong>. "
                f"We have prepared the complete factory specification sheet, certified inspection log, and guaranteed pricing (<strong>${price:.2f}</strong>) below."
            )
        doc_notice_title = "&#128206; Attached Official Document (Quote_Detail.pdf):"
        doc_notice_desc = "For detailed code, OEM interchange part numbers, and complete terms and conditions, <b>please click and view the attached document (<span style='color:#2563eb;font-weight:600;'>Quote_Detail.pdf</span>)</b>."
        btn_text = "Click Here to Complete Order Online"
        footer_text = "Thank you for choosing Yards & Parts Automotive. Valid for 3 days from date of issue.<br>For questions, call dispatch at <b>+1 (413) 406-2764</b> or reply directly to this email."

    # Parse itemized parts if multi-part quote
    parts_list = lead.get("parts")
    if not parts_list and lead.get("items_json"):
        try:
            raw_j = lead["items_json"]
            parts_list = json.loads(raw_j) if isinstance(raw_j, str) else raw_j
        except Exception:
            parts_list = None

    items_breakdown_html = ""
    if parts_list and len(parts_list) > 1:
        items_lines = "".join([
            f"""<div style="padding: 7px 0; border-bottom: 1px dashed #cbd5e1; display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <strong style="color: #0f172a; font-size: 13px;">{idx+1}. {itm.get('part_description', 'Genuine Part')}</strong>
                  <span style="display: block; font-size: 11px; color: #64748b; font-family: monospace; margin-top: 2px;">OEM Part #: {itm.get('part_number', 'OEM')} &bull; Qty: 1</span>
                </div>
                <div style="font-weight: bold; color: #0f172a; font-size: 13px; text-align: right; white-space: nowrap; padding-left: 14px;">
                  ${float(itm.get('price_usd', 0.0)):.2f} USD
                </div>
              </div>"""
            for idx, itm in enumerate(parts_list)
        ])
        items_breakdown_html = f"""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px 16px; margin: 18px 0;">
          <h4 style="margin: 0 0 10px 0; font-size: 12px; color: #475569; text-transform: uppercase; letter-spacing: 0.5px;">Quoted Items Breakdown ({len(parts_list)} Parts):</h4>
          <div style="background: white; border: 1px solid #e2e8f0; border-radius: 4px; padding: 6px 12px;">
            {items_lines}
          </div>
          <div style="margin-top: 10px; display: flex; justify-content: space-between; font-size: 13px; font-weight: bold; color: #0f172a;">
            <span>Parts Subtotal:</span>
            <span style="color: #EB0A1E;">${price:.2f} USD</span>
          </div>
        </div>
        """

    # Clean battlecard_text for HTML
    battlecard_text = (
        battlecard_text
        .replace("{model}", model)
        .replace("{part_description}", part)
        .replace("{part}", part)
        .replace("{customer_name}", name)
    )
    battlecard_html = battlecard_text.replace("\n", "<br>")

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;color:#1e293b;max-width:600px;margin:auto;padding:20px;background:#f8fafc;">

  <div style="background:#1e3a8a;padding:16px 20px;border-radius:6px 6px 0 0;">
    <h2 style="color:white;margin:0;font-size:18px;letter-spacing:0.5px;">YARDS &amp; PARTS AUTOMOTIVE &middot; QUOTATION &amp; FITMENT DISPATCH</h2>
  </div>

  <div style="padding:24px;background:white;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 6px 6px;">
    <p style="font-size:14px;line-height:1.6;color:#1e293b;">{intro}</p>

    {items_breakdown_html}

    <!-- Attached Document Notice -->
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:14px;margin:20px 0;">
      <p style="margin:0;font-size:13px;color:#1e40af;font-weight:bold;">
        {doc_notice_title}
      </p>
      <p style="margin:6px 0 0;font-size:12px;color:#334155;line-height:1.5;">
        {doc_notice_desc}
      </p>
    </div>

    <div style="background:#f8fafc;padding:16px;border-left:4px solid #EB0A1E;border-radius:4px;margin:20px 0;">
      <p style="margin:0;font-size:13px;color:#334155;line-height:1.6;">{battlecard_html}</p>
    </div>

    <!-- Click Here Button (navigates to example cart/checkout URL) -->
    <div style="margin:24px 0 16px;">
      <a href="{checkout_url}"
         style="background:#EB0A1E;color:white;padding:12px 28px;text-decoration:none;border-radius:4px;font-weight:bold;font-size:13px;display:inline-block;">
        {btn_text}
      </a>
    </div>

    <p style="font-size:12px;color:#64748b;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;">
      {footer_text}
    </p>
  </div>

</body>
</html>"""

    plain_intro = (intro
                   .replace("<br><br>", "\n\n")
                   .replace("<br>", "\n")
                   .replace("<strong>", "")
                   .replace("</strong>", ""))

    plain_body = f"""{plain_intro}

---
ATTACHED DOCUMENT:
For detailed code, specifications, and terms, please click and view the attached document (Quote_Detail.pdf).

ORDER ONLINE:
Click Here to proceed: {checkout_url}
---

{battlecard_text}

Reply to this email or call +1 (413) 406-2764 to confirm your order.
"""

    return subject, html_body, plain_body


def send_email_via_smtp(to_email: str, subject: str, html_content: str, plain_content: str = None, pdf_path: str = None) -> dict:
    """Convenience wrapper used by formal quotation endpoints."""
    if plain_content is None:
        plain_content = "Please view the attached official Quote PDF for itemized pricing and specifications."
    return send_email(
        to_email=to_email,
        to_name=to_email.split("@")[0],
        subject=subject,
        html_body=html_content,
        plain_body=plain_content,
        pdf_attachment_path=pdf_path,
    )

