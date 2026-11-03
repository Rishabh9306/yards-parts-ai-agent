"""
cadence_engine.py
-----------------
Core orchestration logic.
Determines WHEN and WHAT to send for each lead in the cadence.

Touch Schedule:
  Touch 1 — Phone call   → Day 0  (same day quote abandoned)
  Touch 2 — SMS          → Day 2
  Touch 3 — Email        → Day 5

Status transitions:
  active → re_engaged (if customer responds positively)
  active → closed_lost (if no response after Touch 3)
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.db import Lead, Touch
from app.battlecards import get_battlecard
from app.comms import twilio_sms, twilio_voice, email_client
from app.crm import zoho_client


# ── Touch schedule config ─────────────────────────────────────────────────────
TOUCH_SCHEDULE = [
    {"touch_number": 1, "channel": "phone", "delay_days": 0},
    {"touch_number": 2, "channel": "sms",   "delay_days": 2},
    {"touch_number": 3, "channel": "email", "delay_days": 5},
]


def enqueue_lead(db: Session, lead_data: dict) -> Lead:
    """
    Add a new lead to the cadence system.
    Called when Zoho CRM fires an 'Abandoned Quote' webhook.

    Args:
        db:        SQLAlchemy session
        lead_data: dict from Zoho webhook payload

    Returns:
        The created Lead object.
    """
    # Check if this deal is already in cadence (idempotent)
    existing = db.query(Lead).filter(
        Lead.zoho_deal_id == lead_data.get("deal_id")
    ).first()

    if existing:
        print(f"Lead already in cadence: deal_id={lead_data.get('deal_id')}")
        return existing

    lead = Lead(
        zoho_deal_id     = lead_data.get("deal_id"),
        customer_name    = lead_data.get("customer_name", "Customer"),
        phone            = lead_data.get("phone"),
        email            = lead_data.get("email"),
        part_number      = lead_data.get("part_number"),
        part_description = lead_data.get("part_description"),
        model            = lead_data.get("model"),
        quote_value_usd  = lead_data.get("quote_value_usd"),
        battlecard       = lead_data.get("battlecard", "warranty"),
        category         = lead_data.get("category"),
        status           = "active",
        quote_date       = datetime.utcnow(),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Schedule touch records
    for touch_config in TOUCH_SCHEDULE:
        scheduled = datetime.utcnow() + timedelta(days=touch_config["delay_days"])
        touch = Touch(
            lead_id      = lead.id,
            touch_number = touch_config["touch_number"],
            channel      = touch_config["channel"],
            scheduled_at = scheduled,
            outcome      = "pending",
        )
        db.add(touch)

    db.commit()
    print(f"Lead {lead.id} enqueued. Touches scheduled: Day 0 (phone), Day 2 (SMS), Day 5 (email)")
    return lead


def execute_due_touches(db: Session):
    """
    Called by the scheduler every 15 minutes.
    Finds all 'pending' touches that are due and executes them.
    """
    now = datetime.utcnow()

    due_touches = (
        db.query(Touch)
        .join(Lead)
        .filter(
            Touch.outcome == "pending",
            Touch.scheduled_at <= now,
            Lead.status == "active",
        )
        .all()
    )

    print(f"[{now.isoformat()}] Found {len(due_touches)} due touches.")

    for touch in due_touches:
        lead = touch.lead
        try:
            result = dispatch_touch(touch, lead)
            touch.sent_at         = datetime.utcnow()
            touch.outcome         = result.get("outcome", "sent")
            touch.message_sid     = result.get("sid", "")
            touch.battlecard_used = lead.battlecard
            db.commit()

            # Log activity back to Zoho CRM
            if lead.zoho_deal_id:
                try:
                    note = (
                        f"Cadence Touch {touch.touch_number} ({touch.channel}) sent. "
                        f"Outcome: {touch.outcome}. "
                        f"Battlecard: {touch.battlecard_used}"
                    )
                    zoho_client.add_activity_note(
                        deal_id=lead.zoho_deal_id,
                        note=note,
                        title=f"Touch {touch.touch_number} — {touch.channel.title()}"
                    )
                except Exception as crm_err:
                    print(f"Warning: Zoho note update skipped: {crm_err}")

        except Exception as e:
            touch.outcome = "failed"
            touch.notes   = str(e)
            db.commit()
            print(f"Touch {touch.id} failed: {e}")

    # Close out leads where all 3 touches are done with no re-engagement
    _expire_inactive_leads(db)


def dispatch_touch(touch: Touch, lead: Lead) -> dict:
    """
    Send the actual message for a touch.
    Returns dict with outcome + optional Twilio SID.
    """
    battlecard_text = get_battlecard(
        key=lead.battlecard,
        channel=touch.channel,
        model=lead.model or "your vehicle",
        part_description=lead.part_description or "the part",
    )

    items_list = []
    if lead.items_json:
        try:
            items_list = json.loads(lead.items_json) if isinstance(lead.items_json, str) else lead.items_json
        except Exception:
            items_list = []

    lead_dict = {
        "id":               lead.id,
        "customer_name":    lead.customer_name,
        "model":            lead.model,
        "part_description": lead.part_description,
        "part_number":      lead.part_number,
        "quote_value_usd":  lead.quote_value_usd,
        "preferred_language": getattr(lead, "preferred_language", "en"),
        "parts":            items_list if items_list else None,
        "items_json":       lead.items_json,
    }

    if touch.channel == "phone":
        if not lead.phone:
            return {"outcome": "skipped_no_phone"}
        result = twilio_voice.make_call(
            to_number=lead.phone,
            lead_id=lead.id,
            touch_number=touch.touch_number,
            call_script=battlecard_text,
        )
        return {"outcome": "sent", "sid": result.get("sid")}

    elif touch.channel == "sms":
        if not lead.phone:
            return {"outcome": "skipped_no_phone"}
        body = twilio_sms.build_sms_body(lead_dict, touch.touch_number, battlecard_text, lang=lead_dict["preferred_language"])
        result = twilio_sms.send_sms(to_number=lead.phone, body=body)
        return {"outcome": "sent", "sid": result.get("sid")}

    elif touch.channel == "email":
        if not lead.email:
            return {"outcome": "skipped_no_email"}

        # Count prior sent email touches to see if 2+ emails were already delivered
        prior_emails = (
            lead.touches
            if hasattr(lead, "touches") and lead.touches
            else []
        )
        emails_sent = sum(1 for t in prior_emails if t.channel == "email" and t.outcome in ("sent", "delivered", "opened"))
        is_discount_offer = emails_sent >= 2 or touch.touch_number >= 3

        subject, html_body, plain_body = email_client.build_email(
            lead_dict, touch.touch_number, battlecard_text, is_discount_offer=is_discount_offer
        )

        # Generate official Quote_Detail.pdf so it is always physically attached to the email
        from app.comms.pdf_generator import create_quote_pdf_for_lead
        pdf_path = None
        try:
            pdf_path = create_quote_pdf_for_lead(lead_dict, is_discount_offer=is_discount_offer, discount_pct=4.0)
        except Exception as pdf_err:
            print(f"[CADENCE PDF WARNING] Could not generate Quote_Detail.pdf: {pdf_err}")

        result = email_client.send_email(
            to_email=lead.email,
            to_name=lead.customer_name,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            pdf_attachment_path=pdf_path,
        )
        return {"outcome": "sent", "sid": result.get("message_id")}

    return {"outcome": "unknown_channel"}


def mark_re_engaged(db: Session, lead_id: int):
    """Call this when a customer responds positively (e.g. replies YES to SMS)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.status = "re_engaged"
        lead.updated_at = datetime.utcnow()
        # Cancel any pending future cadence touches immediately so system never spams
        db.query(Touch).filter(Touch.lead_id == lead_id, Touch.outcome == "pending").update({"outcome": "cancelled"})
        db.commit()
        if lead.zoho_deal_id:
            try:
                zoho_client.update_deal_stage(
                    lead.zoho_deal_id,
                    stage="Re-Engaged",
                    notes="Customer responded to cadence follow-up."
                )
            except Exception as crm_err:
                print(f"Warning: Zoho deal stage update skipped: {crm_err}")


def _expire_inactive_leads(db: Session):
    """Mark leads as closed_lost if all 3 touches are done and still no re-engagement."""
    active_leads = db.query(Lead).filter(Lead.status == "active").all()
    for lead in active_leads:
        all_touches = db.query(Touch).filter(Touch.lead_id == lead.id).all()
        if len(all_touches) == 3 and all(t.outcome not in ("pending",) for t in all_touches):
            lead.status = "closed_lost"
            db.commit()
            if lead.zoho_deal_id:
                try:
                    zoho_client.update_deal_stage(
                        lead.zoho_deal_id,
                        stage="Closed Lost",
                        notes="No response after 3-touch cadence."
                    )
                except Exception as crm_err:
                    print(f"Warning: Zoho deal stage update skipped: {crm_err}")
