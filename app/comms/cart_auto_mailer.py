"""
comms/cart_auto_mailer.py
-------------------------
Automated Cart Abandonment Mailing Engine.
Completely separate from the live rep voice & SMS cadence.

Cadence Schedule:
  - Day 0 (End of Day): Initial cart recovery — items saved in cart, prompt to purchase
  - Day 3: Friendly reminder — inventory reserved, 30+90d warranty, prompt to order
  - Day 4: Limited-time 4% discount incentive — coupon YARDS4 applied, prompt to checkout
  - Day 6: Final call — coupon and warehouse hold expiring in 24 hours
"""

import json
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.db import CartAbandonment, CartEmailLog
from app.comms import email_client, pdf_generator

CHECKOUT_BASE_URL = "https://yardsparts.com/"


def build_cart_email(cart: CartAbandonment, day_step: int) -> tuple:
    """
    Constructs the personalized HTML email for the specified day step.

    Returns:
        (subject, html_body, plain_body, is_discount_offer, discount_pct)
    """
    name = cart.customer_name or "Valued Customer"
    model = cart.model or "Vehicle"
    part = cart.part_description or "Automotive Parts"
    total_val = cart.total_value_usd or 0.0
    disc_val = cart.discounted_value_usd or round(total_val * 0.96, 2)
    savings = round(total_val - disc_val, 2)
    checkout_url = CHECKOUT_BASE_URL

    is_discount_offer = day_step in (4, 6)
    discount_pct = 4.0 if is_discount_offer else 0.0

    # Parse items list for display
    try:
        items = json.loads(cart.items_json) if cart.items_json else []
    except Exception:
        items = []

    if not items:
        items = [{"part_description": f"{model} {part}", "part_number": cart.part_number or "OEM", "price_usd": total_val}]

    items_html_rows = "".join([
        f"""<tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#0f172a;">
            <strong>{item.get('part_description', part)}</strong>
            <span style="display:block;font-size:11px;color:#64748b;font-family:monospace;">OEM: {item.get('part_number', 'Genuine')}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:center;font-size:13px;color:#475569;">1</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-size:13px;font-weight:bold;color:#0f172a;">${float(item.get('price_usd', total_val)):.2f}</td>
        </tr>"""
        for item in items
    ])

    if day_step == 0:
        # Day 0: End of Day Cart Recovery
        subject = f"Complete Your Order: {model} {part} — Your Cart is Waiting"
        badge_text = "DAY 0 &bull; CART RECOVERY"
        badge_bg = "#f1f5f9"
        badge_color = "#334155"
        headline = "Your Yards & Parts Cart is Waiting"
        intro_text = (
            f"Hi {name},<br><br>"
            f"We noticed you added the <strong>{part}</strong> for your <strong>{model}</strong> to your online cart earlier today, "
            f"but you haven't completed your order yet.<br><br>"
            f"We've safely saved your cart and placed a temporary hold on this specific unit in our regional distribution warehouse "
            f"so it won't sell out to another customer. Our engineering team has already verified OEM fitment specifications for your {model}."
        )
        action_button_text = "Click Here to Complete Your Order Online"
        highlight_box = (
            "<p style='margin:0;font-size:13px;color:#334155;line-height:1.6;'>"
            "<strong>📦 Reserved Inventory:</strong> Your parts are held in stock. Complete checkout today to receive "
            "guaranteed 24-hour dispatch and direct courier tracking."
            "</p>"
        )

    elif day_step == 3:
        # Day 3: Reminder to Place Order
        subject = f"Reminder: Your {model} {part} is reserved in stock — Yards & Parts Automotive"
        badge_text = "DAY 3 &bull; STOCK RESERVATION REMINDER"
        badge_bg = "#eff6ff"
        badge_color = "#1d4ed8"
        headline = "Friendly Reminder: Your Reserved Parts Are Waiting"
        intro_text = (
            f"Hi {name},<br><br>"
            f"This is a quick friendly reminder regarding the <strong>{part}</strong> ({model}) currently saved in your cart.<br><br>"
            f"This unit has passed our certified 4-point hydraulic bench test and is packaged ready for immediate dispatch. "
            f"Every single order we ship includes our full <strong>30-day direct fitment guarantee</strong> plus <strong>90-day mechanical replacement coverage</strong>.<br><br>"
            f"Are you or your workshop ready to get this installed this week?"
        )
        action_button_text = "Click Here to Place Your Order Now"
        highlight_box = (
            "<p style='margin:0;font-size:13px;color:#1e3a8a;line-height:1.6;'>"
            "<strong>🛡️ Peace of Mind Guarantee:</strong> 30-day fitment guarantee + 90-day mechanical parts coverage. "
            "If your mechanic has any questions on OEM cross-reference, our specialists are on standby."
            "</p>"
        )

    elif day_step == 4:
        # Day 4: 4% Limited-Time Discount
        subject = f"Special 4% Trade Discount Unlocked on Your Cart: {model} {part}"
        badge_text = "DAY 4 &bull; EXCLUSIVE 4% TRADE DISCOUNT"
        badge_bg = "#ecfdf5"
        badge_color = "#047857"
        headline = "Exclusive 4% Commercial Discount Applied to Your Cart!"
        intro_text = (
            f"Hi {name},<br><br>"
            f"Because you've been reviewing this repair for your <strong>{model}</strong> and we want to help you get your vehicle back on the road, "
            f"our sales dispatch manager has authorized an <strong>exclusive 4% commercial trade discount</strong> on your cart!<br><br>"
            f"Your cart total has been reduced from <s>${total_val:.2f}</s> to <strong>${disc_val:.2f} USD</strong> "
            f"(saving you <strong>${savings:.2f}</strong>) using coupon code <strong>YARDS4</strong>.<br><br>"
            f"Plus, we've included <strong>Free Priority Express Freight</strong> with live carrier tracking."
        )
        action_button_text = "Click Here to Claim 4% Off & Complete Order"
        highlight_box = (
            f"<p style='margin:0;font-size:13px;color:#065f46;line-height:1.6;'>"
            f"<strong>🎉 Limited-Time Coupon Active:</strong> Use coupon <strong>YARDS4</strong> at checkout to lock in "
            f"your discounted rate of <strong>${disc_val:.2f} USD</strong> (Save ${savings:.2f}) + Free Express Shipping."
            f"</p>"
        )

    else:
        # Day 6: Final Call / Coupon Expiring
        subject = f"Final Call: Your 4% Discount Coupon on {model} {part} Expires Today"
        badge_text = "DAY 6 &bull; FINAL CALL &bull; COUPON EXPIRING"
        badge_bg = "#fef2f2"
        badge_color = "#b91c1c"
        headline = "Final Notice: Your 4% Coupon & Cart Hold Expire Today"
        intro_text = (
            f"Hi {name},<br><br>"
            f"This is your final notice regarding the 4% promotional trade discount (Coupon: <strong>YARDS4</strong>) "
            f"for your <strong>{model} {part}</strong>.<br><br>"
            f"Our 24-hour warehouse reservation on this certified unit will officially expire at the end of the day today. "
            f"After today, this unit will be released back to our public dealer pool and pricing will revert to standard catalog rates.<br><br>"
            f"If you still need this component for your vehicle, please finalize your order now to lock in your discounted rate of <strong>${disc_val:.2f} USD</strong>."
        )
        action_button_text = "Click Here to Finalize Order Before Expiration"
        highlight_box = (
            "<p style='margin:0;font-size:13px;color:#991b1b;line-height:1.6;'>"
            "<strong>⏳ Last Chance Notice:</strong> The 4% discount code <strong>YARDS4</strong> and reserved warehouse allocation "
            "will be decommissioned tonight. Do not miss this opportunity to save on your OEM replacement."
            "</p>"
        )

    # Price summary in table
    if is_discount_offer:
        price_summary_html = f"""
        <tr>
          <td colspan="2" style="padding:8px 12px;text-align:right;font-size:12px;color:#64748b;">Standard Subtotal:</td>
          <td style="padding:8px 12px;text-align:right;font-size:12px;color:#64748b;text-decoration:line-through;">${total_val:.2f}</td>
        </tr>
        <tr>
          <td colspan="2" style="padding:8px 12px;text-align:right;font-size:12px;color:#16a34a;font-weight:bold;">4% Trade Discount (YARDS4):</td>
          <td style="padding:8px 12px;text-align:right;font-size:12px;color:#16a34a;font-weight:bold;">-${savings:.2f}</td>
        </tr>
        <tr>
          <td colspan="2" style="padding:8px 12px;text-align:right;font-size:12px;color:#0f172a;">Priority Express Freight:</td>
          <td style="padding:8px 12px;text-align:right;font-size:12px;color:#16a34a;font-weight:bold;">FREE</td>
        </tr>
        <tr style="background:#f8fafc;">
          <td colspan="2" style="padding:10px 12px;text-align:right;font-size:14px;font-weight:bold;color:#0f172a;">Total Payable:</td>
          <td style="padding:10px 12px;text-align:right;font-size:15px;font-weight:bold;color:#EB0A1E;">${disc_val:.2f} USD</td>
        </tr>
        """
    else:
        price_summary_html = f"""
        <tr>
          <td colspan="2" style="padding:8px 12px;text-align:right;font-size:12px;color:#0f172a;">Subtotal:</td>
          <td style="padding:8px 12px;text-align:right;font-size:12px;color:#0f172a;">${total_val:.2f}</td>
        </tr>
        <tr>
          <td colspan="2" style="padding:8px 12px;text-align:right;font-size:12px;color:#0f172a;">Priority Express Freight:</td>
          <td style="padding:8px 12px;text-align:right;font-size:12px;color:#16a34a;font-weight:bold;">FREE</td>
        </tr>
        <tr style="background:#f8fafc;">
          <td colspan="2" style="padding:10px 12px;text-align:right;font-size:14px;font-weight:bold;color:#0f172a;">Total Payable:</td>
          <td style="padding:10px 12px;text-align:right;font-size:15px;font-weight:bold;color:#0f172a;">${total_val:.2f} USD</td>
        </tr>
        """

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;max-width:620px;margin:auto;padding:24px;background:#f8fafc;">

  <!-- Header Banner -->
  <div style="background:#1e3a8a;padding:18px 24px;border-radius:8px 8px 0 0;display:flex;align-items:center;justify-content:space-between;">
    <h2 style="color:white;margin:0;font-size:17px;font-weight:bold;letter-spacing:0.5px;">YARDS &amp; PARTS AUTOMOTIVE &bull; AUTOMATIC CART RECOVERY</h2>
  </div>

  <div style="padding:26px;background:white;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
    
    <!-- Step Badge -->
    <div style="margin-bottom:16px;">
      <span style="display:inline-block;padding:4px 10px;border-radius:4px;font-size:11px;font-weight:bold;letter-spacing:0.5px;background:{badge_bg};color:{badge_color};">
        {badge_text}
      </span>
    </div>

    <h1 style="font-size:19px;color:#0f172a;margin:0 0 14px 0;line-height:1.3;">{headline}</h1>

    <p style="font-size:14px;line-height:1.6;color:#334155;">{intro_text}</p>

    <!-- Attached PDF Notice -->
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:14px;margin:20px 0;">
      <p style="margin:0;font-size:13px;color:#1e40af;font-weight:bold;">
        &#128206; Attached Official Document (Quote_Detail.pdf):
      </p>
      <p style="margin:6px 0 0;font-size:12px;color:#334155;line-height:1.5;">
        For detailed code, specifications, and full order breakdown, 
        <b>please click and view the attached document in this email: (<span style="color:#2563eb;font-weight:600;">Quote_Detail.pdf</span>)</b>.
      </p>
    </div>

    <!-- Cart Items Table -->
    <div style="margin:20px 0;">
      <h3 style="font-size:13px;color:#475569;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 8px 0;">Items in Your Cart:</h3>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
        <thead>
          <tr style="background:#f8fafc;">
            <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e8f0;">Product</th>
            <th style="padding:8px 12px;text-align:center;font-size:11px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e8f0;">Qty</th>
            <th style="padding:8px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e8f0;">Price</th>
          </tr>
        </thead>
        <tbody>
          {items_html_rows}
          {price_summary_html}
        </tbody>
      </table>
    </div>

    <!-- Highlight Box -->
    <div style="background:#f8fafc;padding:14px 16px;border-left:4px solid #EB0A1E;border-radius:4px;margin:20px 0;">
      {highlight_box}
    </div>

    <!-- CTA Button to https://www.yardsparts.com/ -->
    <div style="margin:26px 0 16px;text-align:center;">
      <a href="{checkout_url}"
         style="background:#1e3a8a;color:white;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:bold;font-size:14px;display:inline-block;box-shadow:0 2px 4px rgba(235,10,30,0.25);">
        {action_button_text} &rarr;
      </a>
      <p style="margin:8px 0 0 0;font-size:11px;color:#64748b;">
        Secure SSL Checkout via <a href="{checkout_url}" style="color:#2563eb;text-decoration:none;">yardsparts.com</a>
      </p>
    </div>

    <div style="font-size:12px;color:#64748b;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;line-height:1.5;">
      Yards & Parts Automotive &bull; B2B Salvage Yard Interchange &amp; Quoting Engine<br>
      To speak with a technical fitment specialist, reply directly to this email or call <b>+1 (413) 406-2764</b>.
    </div>

  </div>

</body>
</html>"""

    plain_body = (
        f"{subject}\n\n"
        f"Hi {name},\n\n"
        f"Here is an update regarding your {model} {part} cart.\n\n"
        f"Total: ${disc_val if is_discount_offer else total_val:.2f} USD\n"
        f"Online Checkout: {checkout_url}\n\n"
        f"For detailed code and terms, please view the attached document (Quote_Detail.pdf).\n"
    )

    return subject, html_body, plain_body, is_discount_offer, discount_pct


def send_cart_step_email(cart: CartAbandonment, day_step: int, db: Session) -> dict:
    """
    Executes an email send for a given cart at day_step (0, 3, 4, 6),
    attaches the official Quote_Detail.pdf, and records it in CartEmailLog.
    """
    subject, html_body, plain_body, is_discount, disc_pct = build_cart_email(cart, day_step)

    # Prepare data dictionary for Quote_Detail.pdf generator
    try:
        items = json.loads(cart.items_json) if cart.items_json else []
    except Exception:
        items = []

    lead_dict_for_pdf = {
        "id": cart.id,
        "customer_name": cart.customer_name,
        "email": cart.customer_email,
        "model": cart.model,
        "part_description": cart.part_description,
        "part_number": cart.part_number or "0888580703",
        "quote_value_usd": cart.total_value_usd,
        "parts": items if items else None,
    }

    # Generate Quote_Detail.pdf with official Yards & Parts branding and link
    pdf_path = pdf_generator.create_quote_pdf_for_lead(
        lead_dict_for_pdf,
        is_discount_offer=is_discount,
        discount_pct=disc_pct,
    )

    # Dispatch email via Gmail SMTP
    mail_res = email_client.send_email(
        to_email=cart.customer_email,
        to_name=cart.customer_name,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
        pdf_attachment_path=pdf_path,
    )

    now = datetime.utcnow()
    cart.last_email_sent_at = now
    cart.current_day_step = day_step
    cart.status = f"day{day_step}_sent"

    # Compute next scheduled date
    if day_step == 0:
        cart.next_scheduled_date = cart.cart_created_at + timedelta(days=3)
    elif day_step == 3:
        cart.next_scheduled_date = cart.cart_created_at + timedelta(days=4)
    elif day_step == 4:
        cart.next_scheduled_date = cart.cart_created_at + timedelta(days=6)
    elif day_step == 6:
        cart.next_scheduled_date = None
        cart.status = "day6_final_sent"

    # Log the email
    log_entry = CartEmailLog(
        cart_id=cart.id,
        day_step=day_step,
        email_to=cart.customer_email,
        subject=subject,
        message_id=mail_res.get("message_id", ""),
        status=mail_res.get("status", "sent"),
        pdf_attached=True,
        sent_at=now,
    )
    db.add(log_entry)
    db.commit()

    return {
        "status": "success",
        "cart_id": cart.id,
        "day_step": day_step,
        "subject": subject,
        "to_email": cart.customer_email,
        "email_res": mail_res,
        "pdf_path": pdf_path,
        "next_step": 3 if day_step == 0 else (4 if day_step == 3 else (6 if day_step == 4 else None)),
    }


def advance_cart_day(cart: CartAbandonment, db: Session) -> dict:
    """
    Advances the cart to the next cadence step and triggers the email.
    Day 0 -> Day 3 -> Day 4 -> Day 6.
    """
    if cart.status == "purchased":
        return {"status": "skipped", "message": f"Cart #{cart.id} is already purchased."}

    current = cart.current_day_step or 0
    if cart.status == "cart_abandoned":
        target_step = 0
    elif current == 0:
        target_step = 3
    elif current == 3:
        target_step = 4
    elif current == 4:
        target_step = 6
    else:
        cart.status = "expired"
        db.commit()
        return {"status": "completed", "message": f"Cart #{cart.id} sequence has finished all 4 touches."}

    return send_cart_step_email(cart, target_step, db)
