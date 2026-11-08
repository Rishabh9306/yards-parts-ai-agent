"""
main.py
-------
FastAPI application entry point.
Exposes:
  GET  /                     — Sales Rep Cockpit UI
  GET  /dashboard/rep        — Sales Rep Cockpit UI
  POST /webhook/zoho         — Receives Zoho CRM abandoned quote triggers
  POST /webhook/sms          — Receives inbound SMS replies from Twilio
  POST /twiml/call-start/{id}— Starts the 2-way dynamic voice state machine
  POST /twiml/voice-turn/{id}— Processes speech turns in real-time
  POST /api/leads/test-trigger— One-click trigger for Live Voice / SMS testing
  GET  /api/analytics        — Real-time re-engagement lift & objection stats
  GET  /api/lead-timeline/{id}— Full cross-channel conversation history
  POST /api/sync-zoho        — Syncs metrics & percentages back to Zoho CRM
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

from app.models.db import (
    init_db, get_db, Lead, Touch, CallSession, ConversationMessage, Part,
    CartAbandonment, CartEmailLog, VehicleRecord, QuoteProposal, QuoteLineItem
)
from app.services.vin_service import validate_vin, decode_vin
from app.services.hollander_service import evaluate_compatibility
from app.services.pricing_service import calculate_line_item, calculate_quote_financials
from app.services.freight_service import estimate_freight
from app.services.quote_manager import create_new_quote, get_quote_detail
from app import cadence_engine
from app import voice_dialogue
from app import battlecards
from app.battlecards import list_battlecards, get_battlecard
from app.comms import twilio_voice, twilio_sms, email_client, cart_auto_mailer
from app.crm import zoho_client, webhook_dispatcher

app = FastAPI(
    title="Yards & Parts Automotive Sales Cadence System",
    description="Multi-touch 2-Way Conversational Follow-up Engine for Abandoned Quotes",
    version="2.0.0",
)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/architecture-diagram.png")
def get_architecture_diagram():
    diag_path = STATIC_DIR / "architecture_diagram.png"
    if diag_path.exists():
        return FileResponse(diag_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Diagram not found")
TWIML_BASE_URL = os.getenv("TWIML_BASE_URL", "https://homeland-ride-strain-explanation.trycloudflare.com")


def get_twiml_base_url(request: Request = None) -> str:
    """
    Dynamically returns the active public base URL for Twilio voice webhooks and SMS links.
    Priority:
    1. If request came via public reverse proxy (Cloudflare tunnel), use x-forwarded-host / host.
    2. Read TWIML_BASE_URL directly from .env file so runtime updates are immediate.
    3. Fall back to os.environ or default config.
    """
    if request:
        proto = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host and "127.0.0.1" not in host and "localhost" not in host:
            return f"{proto}://{host}".rstrip("/")
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(os.path.join(BASE_DIR, ".env"))
        if vals.get("TWIML_BASE_URL"):
            return vals["TWIML_BASE_URL"].rstrip("/")
    except Exception:
        pass
    return os.getenv("TWIML_BASE_URL", "https://teams-rights-regions-config.trycloudflare.com").rstrip("/")


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()
    _seed_sample_carts()

    # Scheduler runs every 15 minutes to dispatch due touches
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=_run_scheduler,
        trigger="interval",
        minutes=15,
        id="cadence_scheduler",
    )
    scheduler.start()
    print("Cadence scheduler active (every 15 min).")


def _seed_sample_carts():
    from app.models.db import SessionLocal
    from datetime import timedelta
    db = SessionLocal()
    try:
        if db.query(CartAbandonment).count() == 0:
            now = datetime.utcnow()
            samples = [
                {
                    "cart_token": "CART-1021-0118",
                    "customer_name": "John Miller",
                    "customer_email": "orders@yardsparts.com",
                    "customer_phone": "+15550192834",
                    "model": "FORTUNER",
                    "part_description": "Fortuner Brake Pad Front Set",
                    "part_number": "04465-0K360",
                    "items": [{"part_description": "Fortuner Brake Pad Front Set", "part_number": "04465-0K360", "price_usd": 94.50}],
                    "total_usd": 94.50,
                    "day_step": 0,
                    "status": "day0_sent",
                    "created_at": now - timedelta(hours=6),
                    "next_date": now + timedelta(days=2, hours=18),
                },
                {
                    "cart_token": "CART-1018-0245",
                    "customer_name": "Mike Davis",
                    "customer_email": "orders@yardsparts.com",
                    "customer_phone": "+15550192834",
                    "model": "INNOVA",
                    "part_description": "Toyota Transmission Oil 80W-90, 20 ltr",
                    "part_number": "0888580703",
                    "items": [{"part_description": "Toyota Transmission Oil 80W-90, 20 ltr", "part_number": "0888580703", "price_usd": 140.74}],
                    "total_usd": 140.74,
                    "day_step": 3,
                    "status": "day3_sent",
                    "created_at": now - timedelta(days=3),
                    "next_date": now + timedelta(days=1),
                },
                {
                    "cart_token": "CART-1017-0382",
                    "customer_name": "Sarah Wilson",
                    "customer_email": "orders@yardsparts.com",
                    "customer_phone": "+15550192834",
                    "model": "CRYSTA",
                    "part_description": "Crysta Front Strut Assembly LH",
                    "part_number": "48510-0K150",
                    "items": [{"part_description": "Crysta Front Strut Assembly LH", "part_number": "48510-0K150", "price_usd": 185.00}],
                    "total_usd": 185.00,
                    "day_step": 4,
                    "status": "day4_sent",
                    "created_at": now - timedelta(days=4),
                    "next_date": now + timedelta(days=2),
                },
                {
                    "cart_token": "CART-1015-0491",
                    "customer_name": "Alex Carter",
                    "customer_email": "orders@yardsparts.com",
                    "customer_phone": "+15550192834",
                    "model": "FORTUNER",
                    "part_description": "Fortuner Headlamp Assembly RH LED",
                    "part_number": "81110-0K690",
                    "items": [{"part_description": "Fortuner Headlamp Assembly RH LED", "part_number": "81110-0K690", "price_usd": 210.00}],
                    "total_usd": 210.00,
                    "day_step": 6,
                    "status": "day6_sent",
                    "created_at": now - timedelta(days=6),
                    "next_date": None,
                },
            ]
            for s in samples:
                cart = CartAbandonment(
                    cart_token=s["cart_token"],
                    customer_name=s["customer_name"],
                    customer_email=s["customer_email"],
                    customer_phone=s["customer_phone"],
                    model=s["model"],
                    part_description=s["part_description"],
                    part_number=s["part_number"],
                    items_json=json.dumps(s["items"]),
                    total_value_usd=s["total_usd"],
                    discounted_value_usd=round(s["total_usd"] * 0.96, 2),
                    coupon_code="YARDS4",
                    current_day_step=s["day_step"],
                    status=s["status"],
                    checkout_url="https://yardsparts.com/",
                    cart_created_at=s["created_at"],
                    last_email_sent_at=now - timedelta(hours=2),
                    next_scheduled_date=s["next_date"],
                )
                db.add(cart)
            db.commit()
            print("Seeded 4 initial abandoned carts across Day 0, 3, 4, 6.")
    finally:
        db.close()


def _run_scheduler():
    from app.models.db import SessionLocal
    db = SessionLocal()
    try:
        cadence_engine.execute_due_touches(db)
        cart_auto_mailer.run_automated_scheduler(db)
    finally:
        db.close()


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "sales-cadence", "tunnel_url": get_twiml_base_url(request)}


# ── Dashboard UI ───────────────────────────────────────────────────────────────
@app.get("/landing", response_class=HTMLResponse)
@app.get("/spec", response_class=HTMLResponse)
@app.get("/dashboard/landing", response_class=HTMLResponse)
@app.get("/dashboard/spec", response_class=HTMLResponse)
def spec_landing_page():
    """Yards & Parts AI Agent — specification & product architecture overview."""
    html_file = TEMPLATES_DIR / "landing.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return rep_dashboard()


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard/rep", response_class=HTMLResponse)
def rep_dashboard():
    html_file = TEMPLATES_DIR / "dashboard_rep.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>Rep Dashboard template not found</h1>"


# ── Dynamic 2-Way Voice Call Handlers ──────────────────────────────────────────
@app.get("/twiml/call-start/{session_id}", response_class=PlainTextResponse)
@app.post("/twiml/call-start/{session_id}", response_class=PlainTextResponse)
def twiml_call_start(session_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Twilio connects here upon outbound dial answer.
    Initializes Node 1 (Greeting) with native speech recognition gather in English or Spanish.
    """
    session = db.query(CallSession).filter(CallSession.id == session_id).first()
    if not session:
        return "<Response><Say>Error loading call session.</Say><Hangup/></Response>"

    lang = request.query_params.get("lang", "en-US")
    lead = db.query(Lead).filter(Lead.id == session.lead_id).first()
    effective_base_url = get_twiml_base_url(request)
    twiml = voice_dialogue.generate_initial_greeting(session, lead, effective_base_url, lang=lang)
    return PlainTextResponse(twiml, media_type="application/xml")


@app.post("/twiml/voice-turn/{session_id}", response_class=PlainTextResponse)
@app.get("/twiml/voice-turn/{session_id}", response_class=PlainTextResponse)
async def twiml_voice_turn(session_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Twilio posts SpeechResult here in real-time as customer speaks.
    Evaluates customer intent, runs dialogue state machine, and returns next prompt (bilingual).
    """
    session = db.query(CallSession).filter(CallSession.id == session_id).first()
    if not session:
        return "<Response><Say>Session expired.</Say><Hangup/></Response>"

    lead = db.query(Lead).filter(Lead.id == session.lead_id).first()

    customer_speech = ""
    lang = request.query_params.get("lang", "en-US")
    if request.method == "POST":
        try:
            form = await request.form()
            customer_speech = form.get("SpeechResult", "")
        except Exception:
            pass
    else:
        customer_speech = request.query_params.get("SpeechResult", "")

    print(f"[VOICE TURN] Session #{session_id} | Lang: {lang} | Step: {session.current_step} | Customer said: '{customer_speech}'")

    effective_base_url = get_twiml_base_url(request)
    twiml = voice_dialogue.process_voice_turn(
        session=session,
        lead=lead,
        customer_speech=customer_speech,
        base_url=effective_base_url,
        db=db,
        lang=lang,
    )
    return PlainTextResponse(twiml, media_type="application/xml")


# ── Twilio Call Lifecycle & Status Callback ──────────────────────────────────
@app.post("/webhook/voice-status/{session_id}")
async def voice_status_callback(session_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Twilio posts call status events here (initiated, ringing, answered, completed).
    Detects if the customer missed/declined the call and adapts intelligently
    instead of blindly advancing the cadence.
    """
    form = await request.form()
    call_status = form.get("CallStatus", "").lower()
    call_duration = int(form.get("CallDuration", "0") or 0)
    print(f"[VOICE STATUS] Session #{session_id} | Status: {call_status} | Duration: {call_duration}s")

    session = db.query(CallSession).filter(CallSession.id == session_id).first()
    if not session:
        return PlainTextResponse("ok")

    lead = db.query(Lead).filter(Lead.id == session.lead_id).first()
    if not lead:
        return PlainTextResponse("ok")

    from datetime import timedelta

    # 1. Call went UNANSWERED / MISSED / DECLINED
    if call_status in ("no-answer", "busy", "canceled", "failed"):
        session.status = "missed"
        db.commit()

        # Record timeline event
        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="voice",
            role="system",
            content=f"Outbound call went unanswered (Twilio Status: {call_status}). Cadence paused.",
        ))
        db.commit()

        # Update Touch 1 outcome
        touch_1 = db.query(Touch).filter(Touch.lead_id == lead.id, Touch.touch_number == 1).first()
        if touch_1:
            touch_1.outcome = "no_answer"
            db.commit()

        # Send ONE polite, non-pushy missed call check-in SMS
        first_name = (lead.customer_name or "there").split()[0]
        model = lead.model or "your vehicle"
        missed_call_body = (
            f"Hi {first_name}, Alex from Yards & Parts here — tried giving you a quick call about your {model} quote. "
            f"No worries if you're busy! Feel free to text me back here anytime if you have any questions or want the specs sheet."
        )
        try:
            twilio_sms.send_sms(to_number=lead.phone, body=missed_call_body)
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=missed_call_body,
            ))
            db.commit()
        except Exception as e:
            print(f"Missed call SMS error: {e}")

        # Ensure Touch 2 is scheduled for 48 hours later, NEVER fired immediately!
        touch_2 = db.query(Touch).filter(Touch.lead_id == lead.id, Touch.touch_number == 2).first()
        if touch_2:
            touch_2.scheduled_at = datetime.utcnow() + timedelta(days=2)
            db.commit()

    # 2. Call connected but customer hung up immediately (< 10s) without speaking
    elif call_status == "completed":
        transcript = json.loads(session.transcript or "[]")
        customer_turns = [t for t in transcript if t.get("speaker") == "customer"]

        if not customer_turns and call_duration < 10:
            session.status = "hung_up_early"
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="voice",
                role="system",
                content=f"Call connected for {call_duration}s but customer disconnected before speaking. Cadence waiting.",
            ))
            db.commit()
            touch_2 = db.query(Touch).filter(Touch.lead_id == lead.id, Touch.touch_number == 2).first()
            if touch_2:
                touch_2.scheduled_at = datetime.utcnow() + timedelta(days=2)
                db.commit()
        else:
            session.status = "completed"
            db.commit()
            # Send conclusion summary SMS automatically if not already sent
            try:
                voice_dialogue.send_post_call_summary_sms(session, lead, db)
            except Exception as e:
                print(f"[VOICE STATUS] Error sending post-call summary SMS: {e}")

            # Dispatch outbound CRM webhook event
            try:
                from app.crm.webhook_dispatcher import dispatch_crm_event
                dispatch_crm_event("call.completed", {
                    "sessionId": session.id,
                    "leadId": lead.id,
                    "customerName": lead.customer_name,
                    "customerPhone": lead.phone,
                    "callDurationSec": call_duration,
                    "finalStep": session.current_step,
                    "status": session.status,
                    "negotiatedPrice": session.negotiated_price,
                    "objections": json.loads(session.detected_objections or "[]"),
                    "turnsCount": len(json.loads(session.transcript or "[]")),
                })
            except Exception as e:
                print(f"[CRM Dispatcher] Call event error: {e}")

    return PlainTextResponse("ok")


# ── Catalog & Model Endpoints ────────────────────────────────────────────────
@app.get("/api/catalog/models")
def api_get_catalog_models(db: Session = Depends(get_db)):
    """Returns distinct vehicle models in catalog."""
    rows = db.query(Part.model).distinct().order_by(Part.model).all()
    models = [r[0] for r in rows if r[0]]
    return {"models": models}


@app.get("/api/catalog/parts")
def api_get_catalog_parts(
    model: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    """
    Returns parts filtered strictly by vehicle model and optional search query.
    """
    query = db.query(Part)
    if model:
        query = query.filter(Part.model == model.strip().upper())
    if q and q.strip():
        search_filter = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Part.part_description.ilike(search_filter),
                Part.part_number.ilike(search_filter)
            )
        )
    parts = query.order_by(Part.part_description).all()
    return {
        "count": len(parts),
        "model": model,
        "parts": [
            {
                "id": p.id,
                "part_number": p.part_number,
                "part_description": p.part_description,
                "model": p.model,
                "price_usd": p.price_usd,
                "category": p.category or "General",
            }
            for p in parts
        ]
    }


@app.get("/api/battlecards")
def api_get_battlecards():
    """Returns all 13 battlecards with scripts, icons, and descriptions."""
    return {"battlecards": list_battlecards()}


def sanitize_phone(phone_str: str) -> str:
    if not phone_str:
        return ""
    cleaned = re.sub(r'[^\d+]', '', str(phone_str).strip())
    if not cleaned.startswith("+") and cleaned:
        cleaned = "+" + cleaned
    return cleaned


# ── Test Trigger Tool ─────────────────────────────────────────────────────────
@app.post("/api/leads/test-trigger")
async def api_test_trigger(request: Request, db: Session = Depends(get_db)):
    """
    Triggered from the Rep Dashboard to test a live 2-way call, SMS, or email
    for single or multiple catalog parts with custom contact details.
    """
    payload = await request.json()
    raw_phone = payload.get("phone", "+15550192834")
    phone = sanitize_phone(raw_phone)
    email = payload.get("email") or "orders@yardsparts.com"
    channel = payload.get("channel", "voice")
    model = payload.get("model", "FORTUNER")

    parts = payload.get("parts", [])
    if parts:
        part_numbers = [p.get("part_number", "").strip() for p in parts if p.get("part_number")]
        part_descriptions = [p.get("part_description", "").strip() for p in parts if p.get("part_description")]
        total_price = sum(float(p.get("price_usd", 0.0)) for p in parts)
        part_number = ", ".join(part_numbers) if part_numbers else payload.get("part_number", "0888580703")
        part_description = " + ".join(part_descriptions) if part_descriptions else payload.get("part_description", "OEM / Recycled Part")
        quote_value_usd = round(total_price, 2)
        category = parts[0].get("category", "General") if parts else payload.get("category", "General")
    else:
        part_number = payload.get("part_number", "0888580703")
        part_description = payload.get("part_description", "Automotive Transmission Assembly")
        quote_value_usd = float(payload.get("quote_value_usd", 140.74))
        category = payload.get("category", "Transmission")

    lead = Lead(
        customer_name    = payload.get("customer_name", "Customer"),
        phone            = phone,
        email            = email,
        part_number      = part_number,
        part_description = part_description,
        model            = model,
        quote_value_usd  = quote_value_usd,
        battlecard       = "mileage_concern",
        category         = category,
        items_json       = json.dumps(parts) if parts else "[]",
        status           = "active",
        quote_date       = datetime.utcnow(),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    now = datetime.utcnow()
    from datetime import timedelta

    # Dispatch selected channel immediately and schedule subsequent touches realistically
    if channel == "voice":
        t1 = Touch(lead_id=lead.id, touch_number=1, channel="phone", scheduled_at=now, outcome="in_progress")
        t2 = Touch(lead_id=lead.id, touch_number=2, channel="sms",   scheduled_at=now + timedelta(days=2), outcome="pending")
        t3 = Touch(lead_id=lead.id, touch_number=3, channel="email", scheduled_at=now + timedelta(days=5), outcome="pending")
        db.add_all([t1, t2, t3])
        db.commit()

        call_res = twilio_voice.make_call(
            to_number=phone,
            lead_id=lead.id,
            touch_number=1,
        )
        if call_res.get("status") == "error":
            t1.outcome = "failed"
            db.commit()
            return {
                "status": "error",
                "message": call_res.get("error", "Twilio call dispatch failed"),
            }

        t1.message_sid = call_res.get("sid", "")
        db.commit()
        return {
            "status": "success",
            "message": f"Voice call dialed to {phone}!",
            "sid": call_res.get("sid"),
            "session_id": call_res.get("session_id"),
        }

    elif channel == "sms":
        t1 = Touch(lead_id=lead.id, touch_number=1, channel="phone", scheduled_at=now, outcome="skipped")
        t2 = Touch(lead_id=lead.id, touch_number=2, channel="sms",   scheduled_at=now, outcome="sent")
        t3 = Touch(lead_id=lead.id, touch_number=3, channel="email", scheduled_at=now + timedelta(days=3), outcome="pending")
        db.add_all([t1, t2, t3])
        db.commit()

        lead_dict = {
            "customer_name": lead.customer_name,
            "model": lead.model,
            "part_description": lead.part_description,
            "quote_value_usd": lead.quote_value_usd,
        }
        battlecard_text = get_battlecard(
            "mileage_compression",
            channel="sms",
            model=lead.model or "Vehicle",
            part_description=lead.part_description or "assembly",
        )
        body = twilio_sms.build_sms_body(lead_dict, 1, battlecard_text)
        sms_res = twilio_sms.send_sms(to_number=phone, body=body)

        if sms_res.get("status") == "error":
            t2.outcome = "failed"
            db.commit()
            return {
                "status": "error",
                "message": sms_res.get("error", "Twilio SMS dispatch failed"),
            }

        t2.message_sid = sms_res.get("sid", "")
        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="sms",
            role="assistant",
            content=body,
        ))
        db.commit()

        return {
            "status": "success",
            "message": f"Contextual SMS sent to {phone}!",
            "sid": sms_res.get("sid"),
        }

    elif channel == "email":
        t1 = Touch(lead_id=lead.id, touch_number=1, channel="phone", scheduled_at=now, outcome="skipped")
        t2 = Touch(lead_id=lead.id, touch_number=2, channel="sms",   scheduled_at=now, outcome="skipped")
        t3 = Touch(lead_id=lead.id, touch_number=3, channel="email", scheduled_at=now, outcome="sent")
        db.add_all([t1, t2, t3])
        db.commit()

        items_list = []
        if lead.items_json:
            try:
                items_list = json.loads(lead.items_json) if isinstance(lead.items_json, str) else lead.items_json
            except Exception:
                items_list = []
        if not items_list and payload.get("parts"):
            items_list = payload.get("parts")

        lead_dict = {
            "id": lead.id,
            "customer_name": lead.customer_name,
            "email": lead.email,
            "model": lead.model,
            "part_description": lead.part_description,
            "part_number": lead.part_number,
            "quote_value_usd": lead.quote_value_usd,
            "parts": items_list if items_list else None,
            "items_json": lead.items_json,
        }
        battlecard_text = get_battlecard(
            "mileage_concern",
            channel="email",
            model=lead.model or "Vehicle",
            part_description=lead.part_description or "assembly",
        )
        subject, html_body, plain = email_client.build_email(lead_dict, 1, battlecard_text)

        from app.comms.pdf_generator import create_quote_pdf_for_lead
        pdf_path = create_quote_pdf_for_lead(lead_dict)

        mail_res = email_client.send_email(
            to_email=lead.email,
            to_name=lead.customer_name,
            subject=subject,
            html_body=html_body,
            plain_body=plain,
            pdf_attachment_path=pdf_path,
        )
        t3.message_sid = mail_res.get("message_id", "")
        db.commit()

        return {
            "status": "success",
            "message": f"Assurance email with Quote_Detail.pdf dispatched to {lead.email}!",
            "sid": mail_res.get("message_id"),
        }

    return {"status": "error", "message": "Unknown channel"}


# ── Analytics & Re-engagement Rate Calculations ────────────────────────────────
@app.get("/api/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """
    Computes key cadence percentages and business lift metrics.
    Re-engagement Rate = (Re-engaged / Total Leads) * 100
    """
    total_leads = db.query(Lead).count()
    re_engaged_count = db.query(Lead).filter(
        Lead.status.in_(["re_engaged", "verbal_agreement", "closed_won"])
    ).count()

    rate = (re_engaged_count / total_leads * 100.0) if total_leads > 0 else 0.0

    # Total recovered revenue
    recovered_revenue = db.query(func.sum(Lead.quote_value_usd)).filter(
        Lead.status.in_(["re_engaged", "verbal_agreement", "closed_won"])
    ).scalar() or 0.0

    return {
        "total_leads": total_leads,
        "re_engaged_count": re_engaged_count,
        "re_engagement_rate": round(rate, 1),
        "target_lift": "+24.0%",
        "recovered_revenue": round(recovered_revenue, 2),
    }


# ── Unified Lead Timeline ─────────────────────────────────────────────────────
@app.get("/api/lead-timeline/{lead_id}")
def get_lead_timeline(lead_id: int, db: Session = Depends(get_db)):
    """Returns cross-channel unified transcript for the Rep Cockpit."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.lead_id == lead_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )

    return {
        "lead": {
            "id": lead.id,
            "customer_name": lead.customer_name,
            "model": lead.model,
            "part_description": lead.part_description,
            "status": lead.status,
            "quote_value_usd": lead.quote_value_usd,
        },
        "messages": [
            {
                "id": m.id,
                "channel": m.channel,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


# ── Sync Metrics & Leads to CRM ───────────────────────────────────────────────
@app.post("/api/sync-crm")
@app.post("/api/sync-zoho")
def sync_crm(db: Session = Depends(get_db)):
    """
    Syncs the complete data schema (Leads, Deals, Formal Quote Proposals, 
    and Cadence Conversion Metrics) to CRM systems.
    - Connects directly to the Lead, QuoteProposal, and CartAbandonment schemas.
    - Generates & assigns CRM deal references for unlinked leads.
    - Updates deal stages, activity notes, and re-engagement metrics.
    - Dispatches signed outbound CRM event (crm.sync) with full audit payload.
    - Syncs to Zoho CRM deals if Zoho API is configured.
    """
    analytics = get_analytics(db)

    # 1. Fetch all leads from the Lead schema
    leads = db.query(Lead).all()
    stage_map = {
        "active": "In Cadence",
        "quote_emailed": "Quote Delivered (PDF)",
        "re_engaged": "Re-Engaged",
        "verbal_agreement": "Verbal Agreement",
        "closed_won": "Closed Won",
        "closed_lost": "Closed Lost",
        "callback_scheduled": "Callback Scheduled",
    }

    stage_breakdown = {}
    synced_deals = 0
    zoho_synced = 0

    # Test Zoho connectivity once to prevent repeated timeouts
    zoho_active = False
    try:
        if os.getenv("ZOHO_REFRESH_TOKEN") and os.getenv("ZOHO_CLIENT_ID"):
            token = zoho_client._get_access_token()
            if token:
                zoho_active = True
    except Exception:
        zoho_active = False

    for lead in leads:
        # Ensure lead has a formal CRM deal reference
        if not lead.zoho_deal_id:
            lead.zoho_deal_id = f"CRM-DEAL-{lead.id:04d}"

        stage = stage_map.get(lead.status, "In Cadence")
        stage_breakdown[stage] = stage_breakdown.get(stage, 0) + 1
        lead.updated_at = datetime.utcnow()
        synced_deals += 1

        # Sync to Zoho CRM if live connection is configured and verified for real Zoho deal IDs
        if zoho_active and lead.zoho_deal_id and lead.zoho_deal_id.isdigit():
            try:
                zoho_client.update_deal_stage(
                    deal_id=lead.zoho_deal_id,
                    stage=stage,
                    notes=(
                        f"Yards & Parts CRM Sync | Customer: {lead.customer_name} | "
                        f"Model: {lead.model} | Part: {lead.part_description} | "
                        f"Quote: ${lead.quote_value_usd or 0.0:.2f} USD | "
                        f"Cadence Rate: {analytics['re_engagement_rate']}% | Status: {stage}"
                    )
                )
                zoho_synced += 1
            except Exception:
                pass

    # 2. Fetch all formal Quote Proposals & Line Items
    quotes = db.query(QuoteProposal).all()
    quote_items_count = db.query(QuoteLineItem).count()

    # 3. Fetch Cart Abandonments
    carts = db.query(CartAbandonment).all()

    # Commit any newly assigned deal IDs and timestamps
    db.commit()

    # 4. Dispatch outbound signed CRM webhook event (HMAC-SHA256)
    webhook_event = webhook_dispatcher.dispatch_crm_event("crm.sync", {
        "action": "full_schema_sync",
        "syncedAt": datetime.utcnow().isoformat() + "Z",
        "totalLeadsSynced": len(leads),
        "totalQuotesSynced": len(quotes),
        "totalQuoteItems": quote_items_count,
        "totalCartsSynced": len(carts),
        "analytics": analytics,
        "stageBreakdown": stage_breakdown,
        "sampleDeals": [
            {
                "id": l.id,
                "dealRef": l.zoho_deal_id,
                "customer": l.customer_name,
                "model": l.model,
                "stage": stage_map.get(l.status, "In Cadence"),
                "value": l.quote_value_usd,
            }
            for l in leads[:8]
        ],
        "sampleQuotes": [
            {
                "quoteNumber": q.quote_number,
                "customer": q.customer_name,
                "grandTotal": q.grand_total,
                "status": q.status,
            }
            for q in quotes[:5]
        ]
    })

    return {
        "status": "success",
        "message": f"Synchronized {len(leads)} leads and {len(quotes)} formal quotes to CRM. {len(stage_breakdown)} deal stages mapped. Re-engagement rate: {analytics['re_engagement_rate']}%.",
        "synced_leads": len(leads),
        "synced_quotes": len(quotes),
        "synced_carts": len(carts),
        "zoho_live_synced": zoho_synced,
        "stage_breakdown": stage_breakdown,
        "analytics": analytics,
        "webhook_event_id": webhook_event.get("eventId"),
    }


# ── Inbound SMS Reply Webhook ─────────────────────────────────────────────────
@app.post("/webhook/sms")
async def sms_reply(request: Request, db: Session = Depends(get_db)):
    """
    Twilio posts inbound SMS replies here (and simulator endpoint).
    Supports both Form data (Twilio webhooks) and JSON (Dashboard simulator).
    Handles:
      1. Order Confirmation ("YES", "OK", "CONFIRM") with explicit Expected Delivery Date
      2. Dynamic SMS Objection Handling (Warranty, Pricing, Mileage) via Battlecards
    """
    from_number = ""
    body = ""

    content_type = request.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            data = await request.json()
            from_number = data.get("From") or data.get("from") or data.get("phone", "")
            body = str(data.get("Body") or data.get("body") or data.get("text", "")).strip()
        except Exception as e:
            print(f"JSON parse error: {e}")
    else:
        try:
            form = await request.form()
            from_number = form.get("From", "")
            body = str(form.get("Body", "")).strip()
        except Exception as e:
            print(f"Form parse error: {e}")

    print(f"[INBOUND SMS] From {from_number}: {body}")

    lead = db.query(Lead).filter(Lead.phone == from_number).order_by(Lead.id.desc()).first()
    if lead:
        # Record inbound customer message
        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="sms",
            role="customer",
            content=body,
        ))
        db.commit()

        body_upper = body.upper()
        tokens = set(re.findall(r'\b\w+\b', body_upper))

        # 0. EXPLICIT OPT-OUT / NOT INTERESTED ("STOP", "NO", "CANCEL", "UNSUBSCRIBE", "ALTO", "CANCELAR")
        optout_keywords = {"STOP", "UNSUBSCRIBE", "NO", "CANCEL", "WRONG", "QUIT", "ALTO", "PARAR", "CANCELAR", "BAJA"}
        if tokens & optout_keywords:
            lead.status = "closed_lost"
            # Cancel all future pending touches immediately
            db.query(Touch).filter(Touch.lead_id == lead.id, Touch.outcome == "pending").update({"outcome": "cancelled"})
            db.commit()

            first_name = (lead.customer_name or "there").split()[0]
            is_es = getattr(lead, "preferred_language", "en") == "es" or (tokens & {"ALTO", "PARAR", "CANCELAR", "BAJA"})
            if is_es:
                optout_text = f"Entendido, {first_name}. Hemos cancelado esta cotización y removido su número de futuros seguimientos. ¡Que tenga un excelente día!"
            else:
                optout_text = f"No problem at all, {first_name}. We have closed this quote file and removed your number from any further follow-ups. Have a great day!"
            twilio_sms.send_sms(to_number=from_number, body=optout_text)

            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=optout_text,
            ))
            db.commit()

            if lead.zoho_deal_id:
                try:
                    zoho_client.update_deal_stage(lead.zoho_deal_id, stage="Closed Lost", notes="Customer opted out via SMS.")
                except Exception as e:
                    print(f"Zoho stage update error: {e}")

            return {
                "status": "success",
                "message": f"Customer {lead.customer_name} opted out. Cadence terminated.",
                "reply_sent": optout_text,
            }

        # 0.1 EXPLICIT PREFERENCE FOR SPANISH ("ESPAÑOL", "EN ESPAÑOL", "NO HABLO INGLES")
        spanish_keywords = {"ESPAÑOL", "ESPANOL", "SPANISH"}
        if (tokens & spanish_keywords) or "EN ESPAÑOL" in body_upper or "HABLA ESPAÑOL" in body_upper or "NO HABLO INGLES" in body_upper:
            lead.preferred_language = "es"
            db.commit()
            first_name = (lead.customer_name or "Estimado cliente").split()[0]
            model = lead.model or "su vehículo"
            part_desc = lead.part_description or "su repuesto"
            es_reply = f"¡Hola {first_name}! Con gusto. Hemos actualizado sus preferencias para enviarle todas las comunicaciones en español. Su cotización para {model} ({part_desc}) está reservada. ¿Tiene alguna pregunta para nuestro especialista?"
            twilio_sms.send_sms(to_number=from_number, body=es_reply)
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=es_reply,
            ))
            db.commit()
            return {
                "status": "success",
                "message": f"Updated {lead.customer_name} preferred language to Spanish.",
                "reply_sent": es_reply,
            }

        # 1. POSITIVE CONFIRMATION ("YES", "CONFIRM", "SI", "CLARO", etc.)
        positive_keywords = {"YES", "Y", "CONFIRM", "CONFIRMED", "PROCEED", "AGREE", "OK", "SURE", "LOCK", "SI", "SÍ", "CONFIRMO", "CLARO"}
        if tokens & positive_keywords:
            cadence_engine.mark_re_engaged(db, lead.id)

            from datetime import timedelta
            # Calculate estimated 4 business days for delivery
            dispatch_time = datetime.utcnow()
            delivery_date = dispatch_time + timedelta(days=4)
            if delivery_date.weekday() == 5:    # Saturday -> Monday
                delivery_date += timedelta(days=2)
            elif delivery_date.weekday() == 6:  # Sunday -> Monday
                delivery_date += timedelta(days=1)

            eta_date_str = delivery_date.strftime("%A, %b %d")
            order_num = f"TY-{lead.id:04d}"
            final_price = lead.quote_value_usd or 0.0

            if getattr(lead, "preferred_language", "en") == "es":
                confirmation_text = (
                    f"¡ORDEN CONFIRMADA #{order_num}! Su {lead.model} {lead.part_description} "
                    f"está reservado a ${final_price:.2f} USD. "
                    f"Fecha de Entrega Estimada: {eta_date_str} vía Transporte Prioritario. "
                    f"Garantía: 30 días de ajuste + 90 días de cobertura mecánica activa. "
                    f"Le enviaremos el enlace de rastreo tan pronto sea cargado en el camión. ¡Gracias!"
                )
            else:
                confirmation_text = (
                    f"ORDER CONFIRMED #{order_num}! Your {lead.model} {lead.part_description} "
                    f"is locked in at ${final_price:.2f}. "
                    f"Expected Delivery Date: {eta_date_str} via Priority Freight. "
                    f"Warranty: 30-day fitment + 90-day mechanical coverage active. "
                    f"Tracking link will be texted once loaded on the truck. Thank you!"
                )
            twilio_sms.send_sms(to_number=from_number, body=confirmation_text)

            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=confirmation_text,
            ))
            db.commit()

            # Update Zoho CRM deal stage
            if lead.zoho_deal_id:
                try:
                    zoho_client.update_deal_stage(
                        lead.zoho_deal_id,
                        stage="Closed Won",
                        notes=f"Order Confirmed via SMS. Order #{order_num}, Price: ${final_price:.2f}, ETA: {eta_date_str}."
                    )
                except Exception as crm_err:
                    print(f"Zoho sync warning on SMS confirm: {crm_err}")

            return {
                "status": "success",
                "message": f"Order #{order_num} confirmed for {lead.customer_name}. Expected Delivery Date: {eta_date_str}.",
                "reply_sent": confirmation_text,
            }

        # 2. DYNAMIC OBJECTION HANDLING VIA SMS
        detected = battlecards.detect_objection(body)
        if detected:
            battlecard_reply = battlecards.get_battlecard(
                key=detected,
                channel="sms",
                model=lead.model,
                part_description=lead.part_description,
            )
            sms_reply_text = f"{battlecard_reply} Reply YES to lock this in and schedule priority dispatch!"
            twilio_sms.send_sms(to_number=from_number, body=sms_reply_text)

            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=sms_reply_text,
            ))
            db.commit()

            return {
                "status": "success",
                "message": f"Objection '{detected}' addressed via SMS.",
                "reply_sent": sms_reply_text,
            }

        # 3. GENERAL FALLBACK
        fallback_text = (
            f"Hi {lead.customer_name.split()[0]}, our Yards & Parts desk is ready to help with your {lead.model} {lead.part_description} quote. "
            f"Reply YES to confirm your order, or call us back at +1 (413) 406-2764."
        )
        twilio_sms.send_sms(to_number=from_number, body=fallback_text)
        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="sms",
            role="assistant",
            content=fallback_text,
        ))
        db.commit()

        return {
            "status": "success",
            "message": "Fallback response sent via SMS.",
            "reply_sent": fallback_text,
        }

    return PlainTextResponse("", status_code=200)


# ── Zoho CRM Webhook ──────────────────────────────────────────────────────────
@app.post("/webhook/zoho")
async def zoho_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives abandoned quote events from Zoho CRM."""
    payload = await request.json()
    lead_data = {
        "deal_id": payload.get("id") or payload.get("Deal_Id"),
        "customer_name": payload.get("Contact_Name") or payload.get("Deal_Name", "Customer"),
        "phone": payload.get("Phone") or payload.get("Mobile"),
        "email": payload.get("Email"),
        "part_number": payload.get("Part_Number"),
        "part_description": payload.get("Part_Description") or payload.get("Description"),
        "model": payload.get("Toyota_Model") or payload.get("Vehicle_Model") or payload.get("Account_Name"),
        "quote_value_usd": payload.get("Amount"),
        "battlecard": payload.get("Battlecard", "warranty"),
        "category": payload.get("Part_Category"),
    }
    lead = cadence_engine.enqueue_lead(db, lead_data)
    return {"message": "Lead enqueued", "lead_id": lead.id}


# ── Lead Info ─────────────────────────────────────────────────────────────────
@app.get("/leads")
def list_leads(db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.id.asc()).all()
    out = []
    for l in leads:
        try:
            items = json.loads(l.items_json) if l.items_json else []
        except Exception:
            items = []
        if not items:
            items = [{
                "part_description": l.part_description or "OEM / Recycled Part",
                "part_number": l.part_number or "0888580703",
                "category": l.category or "Genuine Assembly",
                "price_usd": l.quote_value_usd or 0.0,
            }]
        out.append({
            "id": l.id,
            "customer_name": l.customer_name,
            "model": l.model,
            "part_description": l.part_description,
            "part_number": l.part_number,
            "category": l.category,
            "battlecard": l.battlecard,
            "status": l.status,
            "quote_value_usd": l.quote_value_usd,
            "quote_date": l.quote_date,
            "phone": l.phone,
            "email": l.email,
            "items": items,
            "items_count": len(items),
        })
    return out


@app.get("/lead/{lead_id}")
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    touches = db.query(Touch).filter(Touch.lead_id == lead_id).order_by(Touch.touch_number).all()
    return {
        "id": lead.id,
        "customer_name": lead.customer_name,
        "model": lead.model,
        "part_description": lead.part_description,
        "status": lead.status,
        "quote_value_usd": lead.quote_value_usd,
        "phone": lead.phone,
        "email": lead.email,
        "touches": [{"touch_number": t.touch_number, "channel": t.channel, "outcome": t.outcome} for t in touches],
    }


# ── Context-Aware Customer Email Dispatch ──────────────────────────────────────
@app.post("/api/leads/{lead_id}/send-context-email")
def send_context_email(lead_id: int, db: Session = Depends(get_db)):
    """
    Generates and dispatches a context-rich email tailored to the customer's exact
    history (call notes, mechanic consultations, pricing discussions, or missed calls).
    Delivered directly via verified Gmail SMTP.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    target_email = lead.email or "orders@yardsparts.com"
    first_name = (lead.customer_name or "there").split()[0]
    model = lead.model or "Vehicle"
    part_desc = lead.part_description or "assembly"
    quote_price = lead.quote_value_usd or 0.0

    # Retrieve prior conversation messages for context
    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.lead_id == lead_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )
    all_text = " ".join([m.content for m in messages]).lower()

    # Determine how many emails have already been dispatched to this customer
    email_messages = [m for m in messages if m.channel == "email" and m.role == "assistant"]
    email_touches = (
        db.query(Touch)
        .filter(Touch.lead_id == lead_id, Touch.channel == "email", Touch.outcome.in_(["sent", "opened", "delivered"]))
        .all()
    )
    emails_sent_count = max(len(email_messages), len(email_touches))

    # Determine context factors
    mechanic_mentioned = any(k in all_text for k in ["mechanic", "technician", "shop", "bay", "next month", "planning", "rack"])
    unanswered_call = any(k in all_text for k in ["unanswered", "missed", "connected for"])

    # 4% Commercial Trade Discount Rule:
    # Offered via email ONLY after more than two emails have already been sent to the recipient (i.e. emails_sent_count >= 2)
    has_discount_offer = emails_sent_count >= 2
    discount_price = round(quote_price * 0.96, 2)  # 4% commercial trade discount
    discount_savings = round(quote_price * 0.04, 2)

    # Parse individual line items if multi-item quote
    items_list = []
    if lead.items_json:
        try:
            items_list = json.loads(lead.items_json) if isinstance(lead.items_json, str) else lead.items_json
        except Exception:
            items_list = []

    clean_subject_part = f"{len(items_list)} Quoted Parts Package" if (items_list and len(items_list) > 1) else part_desc

    if items_list and len(items_list) > 1:
        items_lines_html = "".join([
            f"""<div style="padding: 6px 0; border-bottom: 1px dashed #cbd5e1; display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                  <strong style="color: #0f172a; font-size: 13px;">{idx+1}. {itm.get('part_description', 'Genuine Part')}</strong>
                  <span style="display: block; font-size: 11px; color: #64748b; font-family: monospace; margin-top: 2px;">OEM Part #: {itm.get('part_number', 'OEM')} &bull; Qty: 1</span>
                </div>
                <div style="font-weight: bold; color: #0f172a; font-size: 13px; text-align: right; white-space: nowrap; padding-left: 14px;">
                  ${float(itm.get('price_usd', 0.0)):.2f} USD
                </div>
              </div>"""
            for idx, itm in enumerate(items_list)
        ])
        component_row = f"""
            <tr>
              <td style="padding: 8px 0; color: #64748b; vertical-align: top; width: 140px;">Quoted Items ({len(items_list)}):</td>
              <td style="padding: 8px 0;">
                <div style="background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 14px;">
                  {items_lines_html}
                </div>
              </td>
            </tr>
        """
        item_mention = f"your {model} ({len(items_list)} components quoted)"
    else:
        component_row = f"""
            <tr><td style="padding: 5px 0; color: #64748b;">Component / Assembly:</td><td style="padding: 5px 0; font-weight: bold;">{part_desc}</td></tr>
        """
        item_mention = f"your {model} {part_desc}"

    if has_discount_offer:
        subject = f"Special 4% Trade Discount Approved: {model} {clean_subject_part} — Yards & Parts Automotive"
        intro_paragraph = (
            f"Hi {first_name},<br><br>"
            f"Following up on your pending quote for <b>{item_mention}</b>.<br><br>"
            f"Because you have been reviewing this repair and we want to help you get your vehicle completed without delay, "
            f"our customer dispatch manager has authorized an <b>exclusive 4% commercial discount offer</b> on your order!<br><br>"
            f"We have reduced your guaranteed price from <s>${quote_price:.2f}</s> to <b>${discount_price:.2f} USD</b> "
            f"(saving ${discount_savings:.2f}), and we have included <b>free priority express freight dispatch</b> with direct carrier tracking."
        )
    elif mechanic_mentioned:
        subject = f"Technical Spec Sheet & OEM Interchange: {model} {clean_subject_part} — Yards & Parts Automotive"
        intro_paragraph = (
            f"Hi {first_name},<br><br>"
            f"Following up on our recent conversation regarding <b>{item_mention}</b>. "
            f"As you mentioned you are reviewing the repair details with your mechanic, we have put together the "
            f"factory specification sheet, OEM interchange numbers, and certified pre-shipment inspection report below "
            f"so you can forward this directly to your shop before making any decisions."
        )
    elif unanswered_call:
        subject = f"Sorry we missed you! {model} {clean_subject_part} Spec Sheet & Quote — Yards & Parts Automotive"
        intro_paragraph = (
            f"Hi {first_name},<br><br>"
            f"Alex here from the Yards & Parts Automotive desk. I tried giving you a quick call earlier regarding the quote for "
            f"<b>{item_mention}</b>. We know shop days can be extremely busy, so we wanted to make sure you had all the "
            f"specifications, pricing, and warranty terms directly in your inbox to review whenever you have a free moment."
        )
    else:
        subject = f"OEM Spec Sheet & Warranty Certificate: {model} {clean_subject_part} (${quote_price:.2f}) — Yards & Parts Automotive"
        intro_paragraph = (
            f"Hi {first_name},<br><br>"
            f"Thank you for contacting Yards & Parts Automotive. We have put together the complete specification sheet, itemized breakdown, and guaranteed "
            f"pricing for <b>{item_mention}</b> (${quote_price:.2f})."
        )

    price_rows = f"""
        <tr><td style="padding: 5px 0; color: #64748b;">Standard Catalog Price:</td><td style="padding: 5px 0; text-decoration: line-through; color: #94a3b8;">${quote_price:.2f} USD</td></tr>
        <tr><td style="padding: 5px 0; color: #16a34a; font-weight: bold;">Special 4% Trade Discount:</td><td style="padding: 5px 0; font-weight: bold; color: #16a34a; font-size: 15px;">${discount_price:.2f} USD</td></tr>
        <tr><td style="padding: 5px 0; color: #64748b;">Discount Offer Status:</td><td style="padding: 5px 0; color: #16a34a; font-weight: 600;">Authorized (Valid 48 Hours) + Free Express Freight</td></tr>
    """ if has_discount_offer else f"""
        <tr><td style="padding: 5px 0; color: #64748b;">Guaranteed Quote:</td><td style="padding: 5px 0; font-weight: bold; color: #dc2626;">${quote_price:.2f} USD</td></tr>
    """

    html_content = f"""
    <div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 620px; line-height: 1.6; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
      <div style="background-color: #1e3a8a; padding: 18px 24px; color: white;">
        <h2 style="margin: 0; font-size: 20px; letter-spacing: 0.5px;">YARDS &amp; PARTS AUTOMOTIVE &middot; CUSTOMER DESK</h2>
        <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Direct Quote &amp; Specification Summary</p>
      </div>
      <div style="padding: 24px;">
        <p>{intro_paragraph}</p>
        
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
          <h3 style="margin: 0 0 10px; font-size: 15px; color: #0f172a;">Part &amp; Order Details</h3>
          <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
            <tr><td style="padding: 5px 0; color: #64748b;">Vehicle Model:</td><td style="padding: 5px 0; font-weight: bold;">{model}</td></tr>
            {component_row}
            {price_rows}
            <tr><td style="padding: 5px 0; color: #64748b;">Warranty Coverage:</td><td style="padding: 5px 0;">30-Day Direct Fitment + 90-Day Mechanical Replacement</td></tr>
            <tr><td style="padding: 5px 0; color: #64748b;">Inspection &amp; Testing:</td><td style="padding: 5px 0;">Certified &lt;80,000 km, 4-point hydraulic bench test</td></tr>
          </table>
        </div>

        <p style="font-size: 13px; color: #475569;">
          <b>No Pressure Promise:</b> We never charge or ship until your mechanic verifies compatibility. Whenever your shop gives the green light, simply reply directly to this email or call our direct line at <b>(413) 406-2764</b> and reference Lead #{lead_id}.
        </p>
        
        <p style="margin-top: 24px; font-size: 13px; color: #64748b;">
          Best regards,<br>
          <b>Alex &middot; Yards &amp; Parts Automotive Specialist</b><br>
          Customer Dispatch Desk
        </p>
      </div>
    </div>
    """

    plain_content = (
        f"Hi {first_name},\n\n"
        f"Following up on your {model} {part_desc} quote. Quoted Value: ${discount_price if has_discount_offer else quote_price:.2f}.\n"
        f"Backed by 30-day fitment + 90-day mechanical warranty.\n"
        f"Reply anytime or call us directly at (413) 406-2764."
    )

    from app.comms.pdf_generator import create_quote_pdf_for_lead
    lead_dict = {
        "id": lead.id,
        "customer_name": lead.customer_name,
        "email": target_email,
        "model": model,
        "part_description": part_desc,
        "part_number": lead.part_number or "0888580703",
        "quote_value_usd": quote_price,
        "parts": items_list if items_list else None,
        "items_json": lead.items_json,
    }
    pdf_path = create_quote_pdf_for_lead(lead_dict, is_discount_offer=has_discount_offer, discount_pct=4.0)

    email_res = email_client.send_email(
        to_email=target_email,
        to_name=lead.customer_name,
        subject=subject,
        html_body=html_content,
        plain_body=plain_content,
        pdf_attachment_path=pdf_path,
    )

    # Record message in conversation timeline
    db.add(ConversationMessage(
        lead_id=lead.id,
        channel="email",
        role="assistant",
        content=f"Context-aware email dispatched to {target_email}: '{subject}'",
    ))
    lead.status = "quote_emailed"
    db.commit()

    return {
        "status": "success",
        "message": f"Contextual email delivered to {target_email}!",
        "subject": subject,
        "email_res": email_res,
    }


# ── Direct Outbound Call to Existing Lead ──────────────────────────────────────
@app.post("/api/leads/{lead_id}/call")
def call_lead(lead_id: int, db: Session = Depends(get_db)):
    """Triggers an outbound call directly to an existing lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead or not lead.phone:
        raise HTTPException(status_code=404, detail="Lead or phone number not found")

    clean_phone = sanitize_phone(lead.phone)
    call_res = twilio_voice.make_call(
        to_number=clean_phone,
        lead_id=lead.id,
        touch_number=1,
    )
    if call_res.get("status") == "error":
        return {
            "status": "error",
            "message": call_res.get("error", "Twilio call dispatch failed"),
        }
    return {
        "status": "success",
        "message": f"Calling {lead.customer_name} at {clean_phone}...",
        "sid": call_res.get("sid"),
        "session_id": call_res.get("session_id"),
    }


# ── Direct Outbound Follow-up SMS to Existing Lead ────────────────────────────
@app.post("/api/leads/{lead_id}/send-sms")
def send_lead_sms(lead_id: int, db: Session = Depends(get_db)):
    """Dispatches a personalized follow-up SMS directly to an existing lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead or not lead.phone:
        raise HTTPException(status_code=404, detail="Lead or phone number not found")

    clean_phone = sanitize_phone(lead.phone)
    first_name = (lead.customer_name or "there").split()[0]
    model = lead.model or "your vehicle"
    part = lead.part_description or "the part"
    price = lead.quote_value_usd or 0.0

    body = (
        f"Hi {first_name}, following up from Yards & Parts regarding your {model} {part} quote (${price:.2f}). "
        f"We've verified OEM fitment & reserved your unit in our warehouse. View specs & complete order online: "
        f"https://yardsparts.com/ or reply here with any questions!"
    )
    sms_res = twilio_sms.send_sms(to_number=clean_phone, body=body)
    if sms_res.get("status") == "error":
        return {
            "status": "error",
            "message": sms_res.get("error", "Twilio SMS dispatch failed"),
        }

    db.add(ConversationMessage(
        lead_id=lead.id,
        channel="sms",
        role="assistant",
        content=body,
    ))
    db.commit()

    return {
        "status": "success",
        "message": f"Follow-up SMS sent to {lead.phone}!",
        "sid": sms_res.get("sid"),
        "body": body,
    }


# ── Manual Touch Trigger ───────────────────────────────────────────────────────
@app.post("/touch/manual/{lead_id}")
def manual_touch(lead_id: int, db: Session = Depends(get_db)):
    touch = (
        db.query(Touch)
        .filter(Touch.lead_id == lead_id, Touch.outcome == "pending")
        .order_by(Touch.touch_number)
        .first()
    )
    if not touch:
        raise HTTPException(status_code=404, detail="No pending touches")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    result = cadence_engine.dispatch_touch(touch, lead)
    touch.sent_at = datetime.utcnow()
    touch.outcome = result.get("outcome", "sent")
    db.commit()
    return {"message": "Touch dispatched", "touch": touch.touch_number, "channel": touch.channel, "result": result}


# ── Automated Cart Mailing System Routes (Completely Separate from Rep Cadence) ───
@app.get("/dashboard/auto-mailer", response_class=HTMLResponse)
@app.get("/auto-mailer", response_class=HTMLResponse)
@app.get("/cart-recovery", response_class=HTMLResponse)
def auto_mailer_dashboard():
    """Serves the dedicated Automated Cart Mailing System dashboard."""
    html_file = TEMPLATES_DIR / "dashboard_auto_mailer.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>Auto-Mailer Dashboard template not found</h1>"


@app.get("/api/auto-mailer/carts")
def get_cart_abandonments(db: Session = Depends(get_db)):
    """
    Returns all abandoned carts tracked by the automatic mailing engine,
    along with summary statistics.
    """
    carts = db.query(CartAbandonment).order_by(CartAbandonment.id.desc()).all()
    total_carts = len(carts)
    active_in_cadence = sum(1 for c in carts if c.status not in ("purchased", "expired"))
    purchased_count = sum(1 for c in carts if c.status == "purchased")
    total_pipeline_val = sum(c.total_value_usd or 0.0 for c in carts)
    recovered_val = sum(c.total_value_usd or 0.0 for c in carts if c.status == "purchased")

    carts_data = []
    for c in carts:
        try:
            items = json.loads(c.items_json) if c.items_json else []
        except Exception:
            items = []
        carts_data.append({
            "id": c.id,
            "cart_token": c.cart_token,
            "customer_name": c.customer_name,
            "customer_email": c.customer_email,
            "customer_phone": c.customer_phone,
            "model": c.model,
            "part_description": c.part_description,
            "part_number": c.part_number,
            "items": items,
            "items_count": len(items) if items else 1,
            "total_value_usd": c.total_value_usd,
            "discounted_value_usd": c.discounted_value_usd,
            "coupon_code": c.coupon_code,
            "current_day_step": c.current_day_step,
            "status": c.status,
            "cart_created_at": c.cart_created_at.isoformat() if c.cart_created_at else None,
            "last_email_sent_at": c.last_email_sent_at.isoformat() if c.last_email_sent_at else None,
            "next_scheduled_date": c.next_scheduled_date.isoformat() if c.next_scheduled_date else None,
            "checkout_url": c.checkout_url,
        })

    return {
        "stats": {
            "total_abandoned": total_carts,
            "active_in_cadence": active_in_cadence,
            "purchased_count": purchased_count,
            "recovery_rate": round((purchased_count / total_carts * 100), 1) if total_carts > 0 else 0.0,
            "total_cart_value": round(total_pipeline_val, 2),
            "recovered_value": round(recovered_val, 2),
        },
        "carts": carts_data,
    }


@app.post("/api/auto-mailer/carts")
async def create_cart_abandonment(request: Request, db: Session = Depends(get_db)):
    """
    Creates a new abandoned cart record (simulates user adding parts to cart and abandoning).
    """
    data = await request.json()
    customer_name = data.get("customer_name") or "John Miller"
    customer_email = data.get("email") or "orders@yardsparts.com"
    customer_phone = data.get("phone") or "+15550192834"
    model = data.get("model") or "FORTUNER"
    parts = data.get("parts") or []

    if parts:
        total_usd = sum(float(p.get("price_usd", 0.0)) for p in parts)
        primary_part = parts[0].get("part_description", "OEM / Recycled Part")
        primary_oem = parts[0].get("part_number", "OEM")
        if len(parts) > 1:
            primary_part += f" + {len(parts) - 1} other item(s)"
    else:
        total_usd = float(data.get("price_usd") or 94.50)
        primary_part = data.get("part_description") or "Fortuner Brake Pad Front Set"
        primary_oem = data.get("part_number") or "04465-0K360"
        parts = [{"part_description": primary_part, "part_number": primary_oem, "price_usd": total_usd}]

    token = f"CART-{datetime.utcnow().strftime('%m%d')}-{abs(hash(customer_name + primary_part)) % 10000:04d}"
    disc_val = round(total_usd * 0.96, 2)

    cart = CartAbandonment(
        cart_token=token,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        model=model,
        part_description=primary_part,
        part_number=primary_oem,
        items_json=json.dumps(parts),
        total_value_usd=round(total_usd, 2),
        discounted_value_usd=disc_val,
        coupon_code="YARDS4",
        current_day_step=0,
        status="cart_abandoned",
        checkout_url="https://yardsparts.com/",
        cart_created_at=datetime.utcnow(),
    )
    db.add(cart)
    db.commit()
    db.refresh(cart)

    auto_trigger = data.get("trigger_day0", True)
    send_res = None
    if auto_trigger:
        send_res = cart_auto_mailer.send_cart_step_email(cart, day_step=0, db=db)

    return {
        "status": "success",
        "cart_id": cart.id,
        "cart_token": cart.cart_token,
        "message": f"Abandoned cart created for {customer_name} ({model}) - Total: ${total_usd:.2f}",
        "day0_email_sent": bool(send_res),
        "send_res": send_res,
    }


@app.post("/api/auto-mailer/carts/{cart_id}/trigger-step")
def trigger_cart_step(cart_id: int, step: int, db: Session = Depends(get_db)):
    """
    Explicitly triggers a specific cadence email (0, 3, 4, 6) for testing.
    """
    cart = db.query(CartAbandonment).filter(CartAbandonment.id == cart_id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    if step not in (0, 3, 4, 6):
        raise HTTPException(status_code=400, detail="Invalid day step. Must be 0, 3, 4, or 6.")

    res = cart_auto_mailer.send_cart_step_email(cart, day_step=step, db=db)
    return res


@app.post("/api/auto-mailer/carts/{cart_id}/advance-day")
def advance_cart(cart_id: int, db: Session = Depends(get_db)):
    """
    Simulates time advancement: advances the cart to the next scheduled day touch
    (Day 0 -> Day 3 -> Day 4 -> Day 6) and sends that day's email with Quote_Detail.pdf.
    """
    cart = db.query(CartAbandonment).filter(CartAbandonment.id == cart_id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    res = cart_auto_mailer.advance_cart_day(cart, db=db)
    return res


@app.post("/api/auto-mailer/carts/{cart_id}/mark-purchased")
def mark_cart_purchased(cart_id: int, db: Session = Depends(get_db)):
    """
    Marks the cart as purchased / converted, immediately halting further email reminders.
    """
    cart = db.query(CartAbandonment).filter(CartAbandonment.id == cart_id).first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    cart.status = "purchased"
    cart.next_scheduled_date = None
    db.commit()
    return {"status": "success", "message": f"Cart #{cart_id} marked as purchased! Cadence stopped."}


@app.get("/api/auto-mailer/carts/{cart_id}/logs")
def get_cart_logs(cart_id: int, db: Session = Depends(get_db)):
    """
    Returns email dispatch logs for a specific cart.
    """
    logs = db.query(CartEmailLog).filter(CartEmailLog.cart_id == cart_id).order_by(CartEmailLog.sent_at.desc()).all()
    return [{
        "id": l.id,
        "day_step": l.day_step,
        "email_to": l.email_to,
        "subject": l.subject,
        "status": l.status,
        "pdf_attached": l.pdf_attached,
        "sent_at": l.sent_at.isoformat() if l.sent_at else None,
    } for l in logs]


@app.post("/api/auto-mailer/run-scheduler")
def run_auto_mailer_scheduler(db: Session = Depends(get_db)):
    """
    Evaluates due scheduled carts and dispatches pending emails.
    """
    now = datetime.utcnow()
    due_carts = db.query(CartAbandonment).filter(
        CartAbandonment.status.notin_(["purchased", "expired"]),
        CartAbandonment.next_scheduled_date != None,
        CartAbandonment.next_scheduled_date <= now,
    ).all()

    dispatched = []
    for c in due_carts:
        r = cart_auto_mailer.advance_cart_day(c, db)
        dispatched.append(r)

    return {"status": "success", "processed_count": len(dispatched), "results": dispatched}


# ── VIN to Hollander Quoting Engine API Endpoints ──────────────────────────────
@app.get("/quoting", response_class=HTMLResponse)
def get_quoting_page():
    """
    Renders the unified VIN-to-Hollander Quoting Flow without any artificial 60-second timers.
    """
    quoting_html_path = TEMPLATES_DIR / "quoting_engine.html"
    if quoting_html_path.exists():
        with open(quoting_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Quoting engine template not found</h1>", status_code=404)


@app.post("/api/vehicles/decode")
async def api_decode_vin(request: Request):
    """
    Validates check digit and decodes VIN via NHTSA vPIC live API.
    """
    data = await request.json()
    vin = data.get("vin", "")
    decoded = decode_vin(vin)
    return decoded


@app.post("/api/compatibility/check")
async def api_check_compatibility(request: Request):
    """
    Evaluates part fitment and Hollander Interchange matching against vehicle build specs.
    """
    data = await request.json()
    vehicle = data.get("vehicle", {})
    category = data.get("category")
    hollander = data.get("hollanderNumber")
    part_query = data.get("partQuery")

    matches = evaluate_compatibility(
        vehicle=vehicle,
        requested_category=category,
        hollander_number=hollander,
        part_query=part_query
    )
    return {"matches": matches, "count": len(matches)}


@app.post("/api/pricing/calculate")
async def api_calculate_pricing(request: Request):
    """
    Computes selling price, margin safeguards, core charges, and discounts.
    """
    data = await request.json()
    res = calculate_line_item(
        unit_cost=float(data.get("unitCost", 0.0)),
        base_list_price=float(data.get("baseListPrice", 0.0)) if data.get("baseListPrice") else None,
        markup_percent=float(data.get("markupPercent", 30.0)),
        minimum_selling_price=float(data.get("minimumSellingPrice", 0.0)),
        minimum_gross_margin_pct=float(data.get("minMarginPercent", 0.0)),
        core_charge=float(data.get("coreCharge", 0.0)),
        discount_percent=float(data.get("discountPercent", 0.0)),
        quantity=int(data.get("quantity", 1))
    )
    return res


@app.post("/api/freight/estimate")
async def api_estimate_freight(request: Request):
    """
    Estimates US zone-based LTL and parcel freight with accessorials.
    """
    data = await request.json()
    res = estimate_freight(
        origin_zip=data.get("originZip", "43215"),
        destination_zip=data.get("destinationZip", "77001"),
        weight_lbs=float(data.get("weightLbs", 50.0)),
        service_type=data.get("serviceType", "LTL_FREIGHT"),
        is_residential=bool(data.get("isResidential", False)),
        requires_liftgate=bool(data.get("requiresLiftgate", False)),
        length_in=float(data.get("lengthIn", 0.0)) if data.get("lengthIn") else None,
        width_in=float(data.get("widthIn", 0.0)) if data.get("widthIn") else None,
        height_in=float(data.get("heightIn", 0.0)) if data.get("heightIn") else None
    )
    return res


@app.post("/api/quotes")
async def api_create_quote(request: Request, db: Session = Depends(get_db)):
    """
    Creates a new formal quote, performs all calculations, generates PDF, and persists to DB.
    """
    data = await request.json()
    try:
        quote = create_new_quote(db, data)
        return quote
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.get("/api/quotes")
def api_list_quotes(db: Session = Depends(get_db)):
    """
    Returns list of recently generated formal quotes.
    """
    quotes = db.query(QuoteProposal).order_by(QuoteProposal.id.desc()).limit(30).all()
    res = []
    for q in quotes:
        res.append({
            "id": q.id,
            "quoteNumber": q.quote_number,
            "customerName": q.customer_name,
            "customerPhone": q.customer_phone,
            "customerEmail": q.customer_email,
            "vehicleSummary": q.vehicle_summary,
            "grandTotal": q.grand_total,
            "status": q.status,
            "pdfUrl": f"/api/quotes/{q.id}/pdf",
            "createdAt": q.created_at.strftime("%Y-%m-%d %H:%M:%S") if q.created_at else None,
        })
    return res


@app.get("/api/quotes/{quote_id}")
def api_get_quote(quote_id: int, db: Session = Depends(get_db)):
    """
    Fetches full quote details by ID.
    """
    q = get_quote_detail(db, quote_id)
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return q


@app.get("/api/quotes/{quote_id}/pdf")
def api_get_quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    """
    Returns the formal PDF quote for viewing or download.
    """
    quote = db.query(QuoteProposal).filter(QuoteProposal.id == quote_id).first()
    if not quote or not quote.pdf_path or not os.path.exists(quote.pdf_path):
        raise HTTPException(status_code=404, detail="Quote PDF not found on disk")
    return FileResponse(
        quote.pdf_path,
        media_type="application/pdf",
        filename=f"{quote.quote_number}.pdf"
    )


@app.post("/api/quotes/{quote_id}/trigger-call")
async def api_quote_trigger_call(quote_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Dispatches outbound Twilio Voice AI call referencing this specific quote & vehicle (Supports English & Spanish).
    """
    quote = db.query(QuoteProposal).filter(QuoteProposal.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_phone:
        raise HTTPException(status_code=400, detail="Quote has no customer phone number")

    lang = "en-US"
    try:
        data = await request.json()
        lang = data.get("language", "en-US")
    except Exception:
        lang = request.query_params.get("language", "en-US")

    lead = Lead(
        customer_name=quote.customer_name,
        phone=quote.customer_phone,
        email=quote.customer_email,
        part_description=f"Quote {quote.quote_number}: {quote.vehicle_summary or 'Vehicle Parts'}",
        model="AUTO",
        quote_value_usd=quote.grand_total,
        status="active"
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    effective_base_url = get_twiml_base_url(request)
    call_res = twilio_voice.place_outbound_call(lead=lead, db=db, base_url=effective_base_url, language=lang)

    # Note: SMS and Email have their own explicit dedicated dispatch buttons in the UI
    # to avoid double-messaging the customer. Only dispatch call here.
    return {
        "status": "call_initiated",
        "quoteNumber": quote.quote_number,
        "language": lang,
        "callResult": call_res,
        "smsSent": False,
        "emailSent": False
    }


@app.post("/api/quotes/{quote_id}/send-sms")
def api_quote_send_sms(quote_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Dispatches Twilio SMS with quote summary and PDF link.
    """
    quote = db.query(QuoteProposal).filter(QuoteProposal.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_phone:
        raise HTTPException(status_code=400, detail="Quote has no customer phone number")

    effective_base_url = get_twiml_base_url(request)
    pdf_public_url = f"{effective_base_url}/api/quotes/{quote.id}/pdf"
    sms_body = (
        f"Hi {quote.customer_name}, here is your Yards & Parts quote {quote.quote_number} "
        f"for {quote.vehicle_summary or 'your vehicle'}. Total: ${quote.grand_total:.2f} USD "
        f"(incl. freight & refundable core deposit). View formal PDF quote: {pdf_public_url}"
    )

    sms_res = twilio_sms.send_sms(to_number=quote.customer_phone, body=sms_body)
    return {"status": "sms_sent", "quoteNumber": quote.quote_number, "smsResult": sms_res}


@app.post("/api/quotes/{quote_id}/send-email")
def api_quote_send_email(quote_id: int, db: Session = Depends(get_db)):
    """
    Sends customer assurance email with attached formal PDF quote.
    """
    quote = db.query(QuoteProposal).filter(QuoteProposal.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_email:
        raise HTTPException(status_code=400, detail="Quote has no customer email address")

    pdf_path = quote.pdf_path if (quote.pdf_path and os.path.exists(quote.pdf_path)) else None
    if not pdf_path:
        from app.services.quote_manager import get_quote_detail
        from app.services.pdf_quote_service import generate_formal_quote_pdf
        try:
            detail = get_quote_detail(db, quote.id)
            if detail:
                os.makedirs("temp_quotes", exist_ok=True)
                pdf_filename = f"Quote_{quote.quote_number}_{int(datetime.utcnow().timestamp())}.pdf"
                pdf_path = f"temp_quotes/{pdf_filename}"
                generate_formal_quote_pdf(detail, pdf_path)
                quote.pdf_path = pdf_path
                db.commit()
        except Exception as e:
            print(f"[QUOTE PDF REGEN WARNING] {e}")

    subject = f"Official Parts Quotation {quote.quote_number} - Yards & Parts Automotive"
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.5;">
        <h2 style="color: #c00;">Yards & Parts Automotive Quotation</h2>
        <p>Dear {quote.customer_name},</p>
        <p>Thank you for inquiring with Yards & Parts. We have verified Hollander interchange compatibility for your vehicle:</p>
        <div style="background: #f4f6f8; padding: 12px; border-left: 4px solid #c00; margin: 15px 0;">
            <b>Vehicle:</b> {quote.vehicle_summary or 'Vehicle on file'}<br/>
            <b>Quotation Number:</b> {quote.quote_number}<br/>
            <b>Total Amount:</b> ${quote.grand_total:.2f} USD (incl. LTL freight & refundable core deposit)
        </div>
        <p>Please find attached your official, itemized B2B quotation PDF for full specifications and terms.</p>
        <p>Best regards,<br/><b>Yards & Parts Sales Team</b><br/>Direct: +1 (713) 898-9475</p>
    </body>
    </html>
    """

    res = email_client.send_email_via_smtp(
        to_email=quote.customer_email,
        subject=subject,
        html_content=html_content,
        pdf_path=pdf_path
    )
    return {"status": "email_sent", "quoteNumber": quote.quote_number, "emailResult": res}


# ── Generic CRM Webhook Audit & Test Endpoints ───────────────────────────────
@app.get("/api/crm/webhook-logs")
def api_get_crm_webhook_logs():
    """
    Returns recent outbound CRM webhook delivery logs with signed payloads.
    """
    from app.crm.webhook_dispatcher import get_recent_webhook_events
    return {"events": get_recent_webhook_events(30)}


@app.post("/api/crm/test-webhook")
async def api_trigger_test_webhook(request: Request):
    """
    Sends a test ping event to Kiran's CRM webhook endpoint.
    """
    from app.crm.webhook_dispatcher import dispatch_crm_event
    data = await request.json()
    event_type = data.get("eventType", "ping.test")
    res = dispatch_crm_event(event_type, {
        "message": "Test ping from Yards & Parts Quoting Platform",
        "customData": data.get("payload", {}),
        "triggeredAt": datetime.utcnow().isoformat() + "Z",
    })
    return {"status": "dispatched", "result": res}


# ── Customer Storefront Web Chat Endpoint ────────────────────────────────────
@app.post("/api/chat/message")
async def api_chat_message(request: Request):
    """
    Handles customer storefront web chat conversations.
    Decodes VINs, checks Hollander fitment, estimates freight, and drafts quotes.
    """
    from app.services.web_chat_service import handle_chat_turn
    data = await request.json()
    message = data.get("message", "")
    context = data.get("context", {})
    language = data.get("language", "en")

    res = handle_chat_turn(message=message, context=context, language=language)
    return res

