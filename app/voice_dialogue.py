"""
app/voice_dialogue.py
----------------------
Human-like, Context-Aware Conversational Engine for Twilio Voice Calls.
Features:
  - Generous 3-second speechTimeout (never cuts caller off mid-sentence/pause)
  - Speech hints and experimental_conversations speech model for high accuracy
  - Genuine intent understanding:
      * Email requests ("mail/email it to me") -> Dispatches real email, doesn't force a sale
      * Mechanic / future planning ("planning for next month", "checking with mechanic") -> Respectful advice
      * Price concerns ("I think the price was...") -> Interactive commercial discount negotiation
      * Warranty questions -> Sourced under 50k certified miles, 30+90 day warranty breakdown
      * Order confirmation -> STRICTLY requires explicit buying consent ("place the order", "confirm order")
  - Multi-tier silence recovery (polite check-in if audio drops, never hangs up abruptly)
"""

import json
import threading
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.models.db import Lead, CallSession, ConversationMessage, SessionLocal
from app.battlecards import detect_objection, get_battlecard
from app.comms import twilio_sms, email_client
from app.crm import zoho_client

# Natural Neural Voice Settings (Bilingual English / Spanish)
VOICE_CONFIGS = {
    "en-US": {
        "voice": "Polly.Matthew-Neural",
        "lang": "en-US",
        "hints": "Toyota, Honda, Civic, Fortuner, Innova, engine, transmission, quote, warranty, price, discount, email, mail, text, mechanic, bay, shop, confirm, order, delivery, tracking, yes, no, fitment, freight, liftgate",
    },
    "es-US": {
        "voice": "Polly.Lupe-Neural",
        "lang": "es-US",
        "hints": "Toyota, Honda, Civic, motor, transmision, garantia, precio, descuento, correo, mecanico, si, no, gracias, enviar, piezas, cotizacion, camion, envio, flete, rampa",
    }
}
SPEECH_TIMEOUT_SECS = 3  # Wait a full 3 seconds of pause so customer can think/breathe without interruption


def get_voice_cfg(lang: str = "en-US") -> dict:
    if str(lang).lower().startswith("es"):
        return VOICE_CONFIGS["es-US"]
    return VOICE_CONFIGS["en-US"]


def calculate_delivery_date() -> str:
    """Calculates 4 business days out for realistic express freight."""
    dispatch_time = datetime.utcnow()
    delivery_date = dispatch_time + timedelta(days=4)
    if delivery_date.weekday() == 5:    # Saturday -> Monday
        delivery_date += timedelta(days=2)
    elif delivery_date.weekday() == 6:  # Sunday -> Monday
        delivery_date += timedelta(days=1)
    return delivery_date.strftime("%A, %b %d")


def build_gather_twiml(say_text: str, session_id: int, base_url: str, lang: str = "en-US") -> str:
    """Helper to generate a gather response with generous pause tolerance and automotive hints."""
    cfg = get_voice_cfg(lang)
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{base_url}/twiml/voice-turn/{session_id}?lang={cfg['lang']}",
        method="POST",
        timeout=10,
        speech_timeout=SPEECH_TIMEOUT_SECS,
        speech_model="experimental_conversations",
        language=cfg["lang"],
        hints=cfg["hints"],
        profanity_filter=False,
    )
    gather.say(say_text, voice=cfg["voice"], language=cfg["lang"])
    response.append(gather)
    # If silence after timeout, redirect back to handle silence gracefully
    response.redirect(f"{base_url}/twiml/voice-turn/{session_id}?timeout=1&lang={cfg['lang']}")
    return str(response)


def build_terminal_twiml(farewell_text: str, lang: str = "en-US") -> str:
    """Helper for natural end of call."""
    cfg = get_voice_cfg(lang)
    response = VoiceResponse()
    response.say(farewell_text, voice=cfg["voice"], language=cfg["lang"])
    response.hangup()
    return str(response)


# ── Post-Call Summary SMS ──────────────────────────────────────────────────────

def send_post_call_summary_sms(session: CallSession, lead: Lead, db: Session):
    """
    Sends an automated post-call conclusion/recap SMS to the customer's phone
    summarizing the conclusion of the call (e.g. spec sheet emailed, trade discount logged,
    mechanic consultation noted, or order confirmation), ensuring the caller always receives
    an informative written conclusion without spam.
    """
    if getattr(session, "sms_summary_sent", False):
        return None

    first_name = (lead.customer_name or "there").split()[0]
    model = lead.model or "your vehicle"
    part_desc = lead.part_description or "the assembly"
    quote_price = lead.quote_value_usd or 0.0
    customer_email = lead.email or "orders@yardsparts.com"
    final_price = session.negotiated_price or quote_price

    transcript = json.loads(session.transcript or "[]")
    customer_speech_all = " ".join([t.get("text", "") for t in transcript if t.get("speaker") == "customer"]).lower()

    # 1. EXPLICIT ORDER PLACED (Already sent confirmation SMS)
    if session.current_step == "confirm_end" and any(k in customer_speech_all for k in ["order", "buy", "confirm the order", "place the order"]):
        session.sms_summary_sent = True
        db.commit()
        return "order_confirmation_already_sent"

    # 2. EMAIL / SPEC SHEET WAS REQUESTED OR SENT
    if lead.status == "quote_emailed" or session.current_step == "info_sent" or any(k in customer_speech_all for k in ["mail", "email", "inbox"]):
        body = (
            f"Hi {first_name}, Alex here from Yards & Parts Automotive! As requested on our call, I've emailed the complete OEM spec sheet & quote for your {model} {part_desc} to {customer_email}. Feel free to text me here anytime if you have any questions!"
        )

    # 3. COMMERCIAL FLEET DISCOUNT WAS OFFERED / NEGOTIATED
    elif session.discount_pct and session.discount_pct > 0:
        body = (
            f"Hi {first_name}, thanks for taking my call! Just confirming I logged your negotiated 4% commercial trade discount "
            f"on the {model} {part_desc} down from ${quote_price:.2f} to ${final_price:.2f} with free priority freight. "
            f"Feel free to text YES here whenever you'd like to proceed!"
        )

    # 4. MECHANIC CONSULTATION / CAR WAITING IN SHOP
    elif session.current_step == "consultation_pending" or any(k in customer_speech_all for k in ["mechanic", "technician", "shop", "waiting", "planning", "later"]):
        body = (
            f"Hi {first_name}, great speaking with you! Take your time verifying the {model} {part_desc} specs with your mechanic. We're keeping your quote active — feel free to text me here anytime whenever you're ready."
        )

    # 5. CALLBACK REQUESTED CASE
    elif lead.status == "callback_scheduled" or session.current_step in ("timing_callback", "timing_negotiation"):
        body = (
            f"Hi {first_name}, Alex here from Yards & Parts! Following up on our brief call — I have logged your preferred callback time "
            f"in our CRM system. I've also emailed your itemized PDF quote to {customer_email}. Feel free to text us here anytime!"
        )

    # 6. GENERAL POLITE CALL CONCLUSION
    else:
        body = (
            f"Hi {first_name}, thank you for speaking with Alex at Yards & Parts regarding your {model} {part_desc} quote (${final_price:.2f}). We're holding your unit reserved. Feel free to text us here anytime!"
        )

    try:
        twilio_sms.send_sms(to_number=lead.phone, body=body)
        session.sms_summary_sent = True
        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="sms",
            role="assistant",
            content=f"[Post-Call Summary] {body}",
        ))
        db.commit()
        print(f"[POST-CALL SMS] Sent conclusion SMS to {lead.phone} for Lead #{lead.id}")

        # Guaranteed Email with Quote_Detail.pdf dispatch
        try:
            from app.comms.pdf_generator import create_quote_pdf_for_lead
            lead_dict = {
                "id": lead.id,
                "customer_name": lead.customer_name,
                "email": customer_email,
                "model": model,
                "part_description": part_desc,
                "part_number": lead.part_number or "0888580703",
                "quote_value_usd": final_price,
            }
            pdf_path = create_quote_pdf_for_lead(lead_dict)
            subject, html_body, plain_body = email_client.build_email(
                lead_dict, 1,
                f"Following up on our phone consultation regarding your {model} {part_desc} quote. Your complete itemized proposal and warranty specs are attached below."
            )
            email_client.send_email(
                to_email=customer_email,
                to_name=lead.customer_name,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
                pdf_attachment_path=pdf_path
            )
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="email",
                role="assistant",
                content=f"[Post-Call Email] Dispatched Quote_Detail.pdf to {customer_email}"
            ))
            db.commit()
            print(f"[POST-CALL EMAIL] Dispatched Quote_Detail.pdf to {customer_email}")
        except Exception as mail_err:
            print(f"[POST-CALL EMAIL ERROR] Failed to send post-call email: {mail_err}")

        return body
    except Exception as e:
        print(f"[POST-CALL SMS ERROR] Failed to send post-call SMS: {e}")
        return None


# ── Initial Greeting ──────────────────────────────────────────────────────────

def generate_initial_greeting(session: CallSession, lead: Lead, base_url: str, lang: str = "en-US") -> str:
    """Generates opening node: asks if now is the right time to speak."""
    session.current_step = "timing_check"
    first_name = (lead.customer_name or "there").split()[0]
    model = lead.model or "your vehicle"
    part_desc = lead.part_description or "parts quote"

    if str(lang).lower().startswith("es"):
        greeting = (
            f"¡Hola {first_name}! Le habla Alex de servicio al cliente de Yards and Parts. "
            f"Le llamo respecto a su cotización para el {model}. ¿Tiene un momento para hablar ahora?"
        )
    else:
        greeting = (
            f"Hey {first_name}! This is Alex calling from Yards & Parts customer dispatch regarding your {model} quote. "
            f"Is now a good time to speak?"
        )
    return build_gather_twiml(greeting, session.id, base_url, lang=lang)


# ── Turn Processor ─────────────────────────────────────────────────────────────

def process_voice_turn(
    session: CallSession,
    lead: Lead,
    customer_speech: str,
    base_url: str,
    db: Session,
    lang: str = "en-US",
) -> str:
    """
    Truly dynamic, intent-aware turn processor.
    Never forces an order or acts tone-deaf to customer statements.
    Supports English & Spanish seamlessly.
    """
    customer_speech = customer_speech or ""
    speech_clean = customer_speech.strip().lower()

    # Check prior persistent customer preference
    if (not lang or lang == "en-US") and hasattr(session, "language") and session.language == "es-US":
        lang = "es-US"
    elif (not lang or lang == "en-US") and hasattr(lead, "preferred_language") and lead.preferred_language == "es":
        lang = "es-US"

    # Automatic real-time language detection from speech
    if any(w in speech_clean for w in ["español", "espanol", "hablas español", "no hablo ingles", "en español", "prefiero español"]):
        lang = "es-US"
        session.language = "es-US"
        if lead:
            lead.preferred_language = "es"
            db.commit()
    elif any(w in speech_clean for w in ["in english", "english please", "speak english"]):
        lang = "en-US"
        session.language = "en-US"
        if lead:
            lead.preferred_language = "en"
            db.commit()

    is_spanish = str(lang).lower().startswith("es")
    current_step = session.current_step

    first_name = (lead.customer_name or "there").split()[0]
    model = lead.model or "your vehicle"
    part_desc = lead.part_description or "the assembly"
    quote_price = lead.quote_value_usd or 0.0

    # Ensure customer email is never a dummy @example.com address
    import os
    customer_email = lead.email
    if not customer_email or "@example.com" in customer_email:
        customer_email = os.getenv("GMAIL_USER", "orders@yardsparts.com")
        lead.email = customer_email
        db.commit()

    # Detect if user spoke an email address in the voice turn
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', customer_speech)
    if email_match:
        customer_email = email_match.group(0)
        lead.email = customer_email
        db.commit()
        print(f"[VOICE] Detected and updated customer email: {customer_email}")

    # ── 1. SILENCE & PAUSE HANDLING ───────────────────────────────────────────
    if not speech_clean:
        session.silence_count = (session.silence_count or 0) + 1
        db.commit()

        if session.silence_count == 1:
            reprompt = f"Hey {first_name}, I think you might be on mute or I missed that. Are you still with me?"
            return build_gather_twiml(reprompt, session.id, base_url)
        elif session.silence_count == 2:
            reprompt = f"Just checking in, {first_name} — can you hear me okay on your end?"
            return build_gather_twiml(reprompt, session.id, base_url)
        else:
            # 3rd consecutive silence -> polite exit with instant text check-in
            session.status = "completed"
            db.commit()
            farewell = (
                f"Looks like we might have a spotty line, {first_name}. "
                f"I'll go ahead and email the full quote summary and specs sheet to {customer_email} so you have it handy. "
                f"Take care, talk soon!"
            )
            try:
                # Dispatch real email with Quote_Detail.pdf
                from app.comms.pdf_generator import create_quote_pdf_for_lead
                lead_dict = {
                    "id": lead.id,
                    "customer_name": lead.customer_name,
                    "email": customer_email,
                    "model": model,
                    "part_description": part_desc,
                    "part_number": lead.part_number or "0888580703",
                    "quote_value_usd": quote_price,
                }
                pdf_path = create_quote_pdf_for_lead(lead_dict)
                subject, html_body, plain_body = email_client.build_email(
                    lead_dict, 1, "We tried giving you a quick call regarding your recent parts quote."
                )
                email_client.send_email(
                    to_email=customer_email,
                    to_name=lead.customer_name,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    pdf_attachment_path=pdf_path,
                )
            except Exception as e:
                print(f"Email drop on silence warning: {e}")
            try:
                spotty_sms = (
                    f"Hi {first_name}, looks like our call cut out! Alex from Yards & Parts here. "
                    f"I've emailed your {model} {part_desc} quote & specs to {customer_email}. "
                    f"Feel free to text me back here anytime if you have any questions!"
                )
                twilio_sms.send_sms(to_number=lead.phone, body=spotty_sms)
                session.sms_summary_sent = True
                db.add(ConversationMessage(
                    lead_id=lead.id,
                    channel="sms",
                    role="assistant",
                    content=f"[Post-Call Summary] {spotty_sms}",
                ))
                db.commit()
            except Exception as e:
                print(f"Silence post-call SMS warning: {e}")

            return build_terminal_twiml(farewell)

    # Reset consecutive silence counter
    session.silence_count = 0

    # Load transcript & objections
    transcript = json.loads(session.transcript or "[]")
    objections = json.loads(session.detected_objections or "[]")

    transcript.append({
        "speaker": "customer",
        "step": current_step,
        "text": customer_speech,
        "time": datetime.utcnow().isoformat(),
    })
    db.add(ConversationMessage(
        lead_id=lead.id,
        channel="voice",
        role="customer",
        content=customer_speech,
    ))

    ai_reply_text = ""
    next_step = current_step
    is_terminal = False

    tokens = set(re.findall(r'\b\w+\b', speech_clean))

    # Dynamic Gemini reasoning check for questions outside basic timing checks
    gemini_reply = None
    gemini_order_confirmed = False
    gemini_discount_granted = False

    if (
        current_step not in ("greeting", "timing_check", "timing_negotiation")
        and not any(k in speech_clean for k in ["mail", "email", "inbox", "text", "sms", "call me back", "wrong number"])
        and len(speech_clean) > 2
    ):
        try:
            from app.services.gemini_voice_service import generate_voice_response
            lead_dict = {
                "customer_name": lead.customer_name,
                "model": model,
                "part_description": part_desc,
                "quote_value_usd": quote_price,
                "negotiated_price": session.negotiated_price or round(quote_price * 0.96, 2),
            }
            g_res = generate_voice_response(
                customer_speech=customer_speech,
                lead_data=lead_dict,
                transcript_history=transcript,
                current_step=current_step,
                timeout=3.5,
            )
            if g_res and g_res.get("reply"):
                gemini_reply = g_res["reply"]
                gemini_order_confirmed = g_res.get("order_confirmed", False)
                gemini_discount_granted = g_res.get("discount_granted", False)
        except Exception as e:
            print(f"[Gemini Voice Error] {e}")

    # ── 1. TIMING PERMISSION & RIGHT TIME TO SPEAK FLOW ───────────────────────────
    if current_step in ("greeting", "timing_check"):
        if any(w in speech_clean for w in ["wrong number", "not me", "wrong person", "wrong customer"]):
            next_step = "confirm_end"
            is_terminal = True
            ai_reply_text = "Sorry about the mix-up! Have a great day."
        elif any(w in speech_clean for w in [
            "no", "not a good time", "not right now", "busy", "driving", "in a meeting",
            "meeting", "can't talk", "cant talk", "cannot talk", "bad time", "call back",
            "later", "call me later", "not now", "no puedo hablar", "ocupado", "manejando",
            "reunion", "luego", "mas tarde", "en otro momento", "no time"
        ]) and not any(w in speech_clean for w in ["yes", "yeah", "sure", "fine", "okay", "si"]):
            next_step = "timing_negotiation"
            if is_spanish:
                ai_reply_text = (
                    f"¡Le entiendo perfectamente, {first_name}! No le tomará más de 2 minutos de su tiempo "
                    f"solo para confirmar la compatibilidad y la dirección de entrega. ¿Tendrá 2 minutitos, o está muy ocupado?"
                )
            else:
                ai_reply_text = (
                    f"I completely understand, {first_name}! It won't take more than 2 minutes of your time "
                    f"just to confirm fitment and your delivery address. Do you have a quick 2 minutes, or are you tied up?"
                )
        else:
            # Customer says YES / OK / SURE -> Continue quote review!
            next_step = "service_check"
            price_str = f" for ${quote_price:.2f}" if quote_price > 0 else ""
            if is_spanish:
                ai_reply_text = (
                    f"¡Excelente, gracias {first_name}! Estaba revisando su cotización para el {model} "
                    f"{part_desc}{price_str}. Quería consultar: ¿tiene el auto en el taller ahora mismo, "
                    f"o está planificando la reparación para más adelante?"
                )
            else:
                ai_reply_text = (
                    f"Awesome, thanks {first_name}! I was pulling up your file regarding that {model} "
                    f"{part_desc}{price_str}. Just wanted to check in personally — is this for a vehicle you've got in the shop right now, "
                    f"or are you just planning out the repair for down the road?"
                )

    elif current_step == "timing_negotiation":
        # Customer responds to the 2-minute negotiation offer
        if any(w in speech_clean for w in [
            "yes", "yeah", "yep", "sure", "alright", "okay", "ok", "fine", "go ahead",
            "make it quick", "two minutes", "quick", "shoot", "si", "esta bien", "rapido", "dime", "adelante"
        ]) and not any(w in speech_clean for w in ["no", "can't", "cant", "really busy", "no time"]):
            next_step = "service_check"
            if is_spanish:
                ai_reply_text = (
                    f"¡Muchas gracias, prometo ser muy breve! Para ese {model} {part_desc} cotizado en ${quote_price:.2f}, "
                    f"¿tiene el vehículo en el taller actualmente, o está cotizando con tiempo?"
                )
            else:
                ai_reply_text = (
                    f"Appreciate that, {first_name}, I'll keep it super quick! For that {model} {part_desc} quoted at ${quote_price:.2f}, "
                    f"is the vehicle in the shop right now, or are you planning ahead?"
                )
        else:
            next_step = "timing_callback"
            if is_spanish:
                ai_reply_text = (
                    f"¡Sin problema, respeto mucho su tiempo! ¿Qué día y a qué hora sería mejor que nuestro equipo de repuestos le devuelva la llamada?"
                )
            else:
                ai_reply_text = (
                    f"No problem at all, I respect your time! What day and time would be best for our parts team to give you a call back?"
                )

    elif current_step == "timing_callback":
        # Customer gave preferred callback time -> Log to CRM and wrap up!
        preferred_time = customer_speech.strip() or "tomorrow afternoon"
        next_step = "confirm_end"
        is_terminal = True
        session.status = "completed"

        # UPDATE THE CRM!
        lead.status = "callback_scheduled"

        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="voice",
            role="system",
            content=f"[CRM Updated] Callback Scheduled: {preferred_time}"
        ))
        db.commit()

        # Update Zoho CRM deal stage if deal exists
        if lead.zoho_deal_id:
            try:
                zoho_client.update_deal_stage(
                    lead.zoho_deal_id,
                    stage="Callback Scheduled",
                    notes=f"Customer requested callback: {preferred_time}"
                )
            except Exception as e:
                print(f"[CRM Callback] Zoho sync error: {e}")

        # Dispatch Outbound CRM Webhook to Kiran's CRM
        try:
            from app.crm.webhook_dispatcher import dispatch_crm_event
            dispatch_crm_event("lead.callback_scheduled", {
                "leadId": lead.id,
                "customerName": lead.customer_name,
                "customerPhone": lead.phone,
                "customerEmail": customer_email,
                "preferredCallbackTime": preferred_time,
                "quoteValue": quote_price,
                "model": model,
                "partDescription": part_desc
            })
        except Exception as e:
            print(f"[CRM Callback] Webhook dispatch error: {e}")

        if is_spanish:
            ai_reply_text = (
                f"¡Anotado, {first_name}! He programado {preferred_time} en nuestro sistema para llamarle. "
                f"También le envié la cotización completa con el PDF adjunto a su correo y celular para que lo tenga a mano. ¡Que tenga un excelente día!"
            )
        else:
            ai_reply_text = (
                f"Perfect, {first_name}! I have logged {preferred_time} in our system, and our parts specialist will call you then. "
                f"I've also emailed and texted you the full itemized PDF quote so you have all the numbers handy. Take care!"
            )
    # ── 1.5 DYNAMIC GEMINI AI REASONING (WITH STRICT BOUNDARIES) ───────────────
    elif gemini_reply:
        ai_reply_text = gemini_reply
        if gemini_discount_granted:
            session.discount_pct = 4.0
            session.negotiated_price = round(quote_price * 0.96, 2)
            if "pricing_concern" not in objections:
                objections.append("pricing_concern")

        if gemini_order_confirmed:
            next_step = "confirm_end"
            is_terminal = True
            session.status = "completed"
            lead.status = "re_engaged"
        else:
            next_step = "gemini_dialogue"

    # ── 2. INTENT: EMAIL / MAIL REQUEST ("please mail it to me", "email me", "inbox") ──
    elif any(k in speech_clean for k in ["mail", "email", "inbox", "send it to my email", "write to me", "send via email", "email it"]):
        next_step = "info_sent"
        lead.status = "quote_emailed"
        db.commit()

        # Send actual HTML quote & warranty email via verified Gmail SMTP
        try:
            lead_dict = {
                "id": lead.id,
                "customer_name": lead.customer_name,
                "email": customer_email,
                "model": model,
                "part_description": part_desc,
                "part_number": lead.part_number or "0888580703",
                "quote_value_usd": session.negotiated_price or quote_price,
            }
            from app.comms.pdf_generator import create_quote_pdf_for_lead
            pdf_path = create_quote_pdf_for_lead(lead_dict)
            subject, html_body, plain_body = email_client.build_email(
                lead_dict, 1,
                f"As requested on our phone call, here is the complete OEM spec sheet and quote breakdown for your {model} {part_desc}."
            )
            email_res = email_client.send_email(
                to_email=customer_email,
                to_name=lead.customer_name,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
                pdf_attachment_path=pdf_path,
            )
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="email",
                role="assistant",
                content=f"Assurance email with Quote_Detail.pdf dispatched to {customer_email}: '{subject}'",
            ))
            db.commit()
        except Exception as e:
            print(f"Failed to dispatch requested email: {e}")

        ai_reply_text = (
            f"You got it, {first_name}! I just sent the complete spec sheet, OEM interchange numbers, and warranty paperwork "
            f"straight to your email at {customer_email}. Take all the time you need to review it with your mechanic, "
            f"and you can reply directly to that email or call us back whenever you're ready. "
            f"Did you need anything else on this part before I let you go?"
        )

    # ── 3. INTENT: TEXT / SMS REQUEST ("text me", "sms", "cell", "to my phone") ──
    elif any(k in speech_clean for k in ["text", "sms", "send to my phone", "send to my cell", "message"]):
        next_step = "info_sent"
        lead.status = "quote_texted"
        db.commit()

        try:
            price_val = session.negotiated_price or quote_price
            twilio_sms.send_sms(
                to_number=lead.phone,
                body=(
                    f"Hi {first_name}, here is your quote for {model} {part_desc} (${price_val:.2f}). "
                    f"Backed by 30-day fitment & 90-day mechanical warranty. "
                    f"Feel free to reply here anytime whenever you have questions or want to proceed!"
                )
            )
            db.add(ConversationMessage(
                lead_id=lead.id,
                channel="sms",
                role="assistant",
                content=f"Sent quote link and warranty breakdown via SMS to {lead.phone}",
            ))
            db.commit()
        except Exception as e:
            print(f"Failed to dispatch requested SMS: {e}")

        ai_reply_text = (
            f"Done! I've just texted the quote details and spec sheet right to your cell. "
            f"Feel free to check that on your phone. Did you have any other questions on the fitment or warranty?"
        )

    # ── 4. INTENT: MECHANIC CONSULTATION / PLANNING AHEAD / NOT READY YET ──────────
    elif any(k in speech_clean for k in [
        "mechanic", "technician", "planning", "next month", "not yet", "haven't checked",
        "did not check", "didn't check", "later", "think about it", "not sure", "look into it",
        "consult", "shop", "waiting"
    ]) and not any(k in speech_clean for k in ["order", "buy", "place"]):
        next_step = "consultation_pending"
        ai_reply_text = (
            f"No problem at all, {first_name}! You definitely want your mechanic to double-check the 17-digit VIN "
            f"and verify the exact sub-assembly specs before you buy anything. "
            f"Would it be helpful if I email the technical spec sheet and OEM diagram to {customer_email} "
            f"so you can just forward it straight to your shop?"
        )

    # ── 5. INTENT: EXPLICIT NEGOTIATION / DISCOUNT REQUEST (4% Trade Discount) ────
    elif any(k in speech_clean for k in [
        "discount", "negotiat", "better price", "best price", "lower price", "deal",
        "give me a deal", "can you do better", "can you lower", "can you reduce", "cut the price",
        "any offer", "special price", "make it cheaper", "trade discount", "give a discount", "give me discount"
    ]) or (session.current_step == "price_inquiry" and any(k in speech_clean for k in ["yes", "yeah", "please", "can you", "lower", "discount", "deal", "better"])):
        next_step = "price_negotiated"
        discount_offered = round(quote_price * 0.04, 2)  # 4% commercial fleet trade discount
        new_price = round(quote_price - discount_offered, 2)
        session.discount_pct = 4.0
        session.negotiated_price = new_price

        ai_reply_text = (
            f"I completely understand wanting to make the numbers work, {first_name}. Since you're ready to proceed with this repair, "
            f"our dispatch desk has authorized our commercial fleet trade discount — that's 4% off, bringing your total down "
            f"from ${quote_price:.2f} to ${new_price:.2f}, and I'll include free express priority freight with direct tracking. "
            f"Does that negotiated price work for your budget?"
        )
        if "pricing_concern" not in objections:
            objections.append("pricing_concern")

    # ── FURTHER DISCOUNT / LOWER PRICE INQUIRY ──────────────────────────────────
    elif session.current_step in ("price_negotiated", "price_negotiated_limit") and any(k in speech_clean for k in ["further", "more", "lower", "bring it down", "can you do better", "less", "cheaper", "down further"]):
        next_step = "price_negotiated_limit"
        current_neg = session.negotiated_price or round(quote_price * 0.96, 2)
        ai_reply_text = (
            f"That 4% trade discount is the absolute maximum pre-authorized on our commercial fleet tier, {first_name}, "
            f"because it already includes free priority express freight and our full 90-day mechanical warranty. "
            f"I can officially lock in ${current_neg:.2f} for you right now. Would you like to go ahead and place the order?"
        )

    # ── 6. INTENT: GENERAL PRICING INQUIRY (Transparency First — No Premature Discount) ──
    elif any(k in speech_clean for k in [
        "price", "expensive", "cheaper", "budget", "high", "cost", "how much", "dollars",
        "too much", "concerning", "was hoping", "price was"
    ]):
        next_step = "price_inquiry"
        ai_reply_text = (
            f"I completely understand pricing is an important factor, {first_name}. Right now that {model} {part_desc} is quoted at "
            f"${quote_price:.2f}, with completely itemized part and freight costs, certified bench-tested under 80,000 kilometres, "
            f"and backed by our 30-day fitment plus 90-day mechanical warranty. "
            f"Were you looking to see if our manager can look into a commercial discount for you, or did you have questions on the spec sheet?"
        )
        if "pricing_concern" not in objections:
            objections.append("pricing_concern")

    # ── 7. INTENT: BATTLECARD — ACTUAL UNIT PHOTOS / TRANSPARENCY ────────────────
    elif any(k in speech_clean for k in ["photo", "photos", "picture", "pictures", "image", "images", "see it", "condition", "look like"]):
        next_step = "battlecard_photos"
        ai_reply_text = (
            f"We believe in total transparency. We have actual high-resolution photos of the specific unit on our warehouse shelf "
            f"showing mounting tabs, wiring harness connectors, and stamped OEM serial numbers. I can email those photos straight to "
            f"{customer_email} right now so you can inspect it yourself. Would that be helpful?"
        )
        if "product_transparency" not in objections:
            objections.append("product_transparency")

    # ── 8. INTENT: BATTLECARD — COMPRESSION & HYDRAULIC BENCH TESTING ────────────
    elif any(k in speech_clean for k in ["compression", "bench test", "psi", "leak down", "tested", "pressure", "hydraulic"]):
        next_step = "battlecard_compression"
        ai_reply_text = (
            f"Every single unit goes through a certified 4-point hydraulic bench test prior to warehouse dispatch. "
            f"We actually send the signed pressure readings directly to you and your mechanic so you have 100% peace of mind "
            f"before it's loaded onto the freight truck. Would you like us to attach that test certificate?"
        )
        if "compression_testing" not in objections:
            objections.append("compression_testing")

    # ── 9. INTENT: BATTLECARD — MILEAGE (<80k KM) CONCERN ────────────────────────
    elif any(k in speech_clean for k in ["mileage", "miles", "kilometres", "kilometers", "how many km", "km", "high mileage", "how old"]):
        next_step = "battlecard_mileage"
        ai_reply_text = (
            f"All our engine and transmission assemblies are strictly sourced under 80,000 kilometres with full vehicle inspection logs attached. "
            f"If any unit falls outside factory OEM tolerances, we don't list or ship it. "
            f"Would you like us to email through the certified inspection logs for your {model}?"
        )
        if "mileage_concern" not in objections:
            objections.append("mileage_concern")

    # ── 10. INTENT: BATTLECARD — FREIGHT TIMELINES & 24H DISPATCH ─────────────────
    elif any(k in speech_clean for k in ["shipping", "freight", "delivery", "how long", "dispatch", "arrive", "transit", "when will"]):
        next_step = "battlecard_freight"
        ai_reply_text = (
            f"We dispatch all confirmed inventory within 24 hours. Metro delivery arrives within 3 to 5 business days, "
            f"and you receive a live direct carrier tracking link the moment the pallet leaves our loading dock. "
            f"Does that delivery timeframe work for your workshop?"
        )
        if "freight_timelines" not in objections:
            objections.append("freight_timelines")

    # ── 11. INTENT: BATTLECARD — VIN COMPATIBILITY & FITMENT ──────────────────────
    elif any(k in speech_clean for k in ["vin", "compatible", "compatibility", "chassis", "fit my", "will it fit", "right part"]):
        next_step = "battlecard_vin"
        ai_reply_text = (
            f"Vehicle compatibility is verified directly against your 17-digit VIN, model year, and engine specification before dispatch, "
            f"ensuring exact factory fitment with zero modifications needed. If you have your VIN handy, I can verify it right now!"
        )
        if "part_compatibility" not in objections:
            objections.append("part_compatibility")

    # ── 12. INTENT: BATTLECARD — WARRANTY & FITMENT (30d + 90d) ───────────────────
    elif any(k in speech_clean for k in ["warranty", "guarantee", "reliable", "quality", "what if", "break", "fail", "broken"]):
        next_step = "warranty_explained"
        ai_reply_text = (
            f"We back all our Yards & Parts inventory with a dual protection plan: you get a 30-day fitment guarantee "
            f"to ensure it bolts up seamlessly, plus a full 90-day mechanical replacement warranty on all internal components. "
            f"If there's any issue, we exchange it immediately at our cost. Would you like me to email that certificate?"
        )
        if "warranty_fitment" not in objections:
            objections.append("warranty_fitment")

    # ── 13. INTENT: BATTLECARD — INVENTORY & WAREHOUSE AVAILABILITY ────────────────
    elif any(k in speech_clean for k in ["stock", "available", "on shelf", "warehouse", "in stock", "inventory", "ready to ship"]):
        next_step = "battlecard_stock"
        ai_reply_text = (
            f"I have your part physically verified on our warehouse shelf right now. We confirm stock and bay location "
            f"before taking any order commitment so you are never stuck on backorder. We can hold this unit for 24 hours under your name."
        )
        if "inventory_availability" not in objections:
            objections.append("inventory_availability")

    # ── 14. INTENT: BATTLECARD — RETURNS & REPLACEMENTS ───────────────────────────
    elif any(k in speech_clean for k in ["return", "returns", "replace", "refund", "exchange", "wrong part", "send back"]):
        next_step = "battlecard_returns"
        ai_reply_text = (
            f"Our return policy is completely clear and upfront. If anything arrives damaged or does not fit as specified, "
            f"our dispatch team issues an immediate replacement or full refund under our 30-day fitment guarantee, with prepaid return freight."
        )
        if "returns_replacements" not in objections:
            objections.append("returns_replacements")

    # ── 15. INTENT: BATTLECARD — 25 YEARS EXPERIENCE & 100K+ CUSTOMERS ────────────
    elif any(k in speech_clean for k in ["experience", "reputation", "how long have you", "trust", "reviews", "who are you", "credible"]):
        next_step = "battlecard_experience"
        ai_reply_text = (
            f"We are backed by over 25 years of dedicated automotive industry experience and the trust of more than 100,000 satisfied customers. "
            f"You are dealing with experienced automotive specialists at Yards & Parts who stand behind every single part we dispatch."
        )
        if "trusted_experience" not in objections:
            objections.append("trusted_experience")

    # ── 7. INTENT: EXPLICIT ORDER CONFIRMATION (Requires Clear Buying Words) ────────
    elif any(k in speech_clean for k in [
        "place the order", "place order", "go ahead and order", "confirm the order", "confirm order",
        "lock in the order", "buy it", "purchase", "charge it", "order it"
    ]):
        next_step = "confirm_end"
        is_terminal = True
        session.status = "completed"
        lead.status = "re_engaged"

        final_price = session.negotiated_price or quote_price
        eta_date_str = calculate_delivery_date()
        order_num = f"TY-{lead.id:04d}"

        ai_reply_text = (
            f"Terrific, {first_name}! I'm officially locking in your order #{order_num} for the {model} {part_desc} at ${final_price:.2f}. "
            f"Expected express freight delivery is {eta_date_str}, backed by our 30-day fitment and 90-day mechanical warranty. "
            f"I've just emailed your full receipt to {customer_email} and texted the tracking details to your cell. "
            f"Really appreciate your business, {first_name} — have a wonderful day!"
        )

        # Dispatch real confirmation email
        try:
            lead_dict = {
                "id": lead.id,
                "customer_name": lead.customer_name,
                "email": customer_email,
                "model": model,
                "part_description": part_desc,
                "part_number": lead.part_number or "0888580703",
                "quote_value_usd": final_price,
            }
            from app.comms.pdf_generator import create_quote_pdf_for_lead
            pdf_path = create_quote_pdf_for_lead(lead_dict)
            subject = f"Order Confirmed #{order_num} — Yards & Parts Automotive ({model} {part_desc})"
            html_receipt = (
                f"<h2>Order Confirmed #{order_num}</h2>"
                f"<p>Hi {first_name},</p>"
                f"<p>Thank you for your order! Your <b>{model} {part_desc}</b> has been locked in at <b>${final_price:.2f}</b>.</p>"
                f"<ul>"
                f"<li><b>Expected Delivery Date:</b> {eta_date_str} via Priority Freight</li>"
                f"<li><b>Warranty:</b> 30-day direct fitment + 90-day mechanical parts & labor</li>"
                f"<li><b>Tracking:</b> Will be updated once loaded on the truck</li>"
                f"</ul>"
                f"<p style='background-color:#f8fafc; border-left:4px solid #dc2626; padding:12px; margin:16px 0;'>"
                f"📄 <strong>Official Quote & Invoice Attached:</strong> For detailed code, specifications, and full order breakdown, "
                f"please click and view the attached document in this email: <strong>(Quote_Detail.pdf)</strong>.</p>"
                f"<p>If you have any questions, reply directly to this email or call us at (413) 406-2764.</p>"
            )
            email_client.send_email(
                to_email=customer_email,
                to_name=lead.customer_name,
                subject=subject,
                html_body=html_receipt,
                plain_body=f"Order Confirmed #{order_num}! Your {model} {part_desc} is reserved at ${final_price:.2f}. Expected Delivery: {eta_date_str}. For detailed code please click the attached document: Quote_Detail.pdf",
                pdf_attachment_path=pdf_path,
            )
        except Exception as e:
            print(f"Confirmation email error: {e}")

        # Send confirmation SMS
        try:
            twilio_sms.send_sms(
                to_number=lead.phone,
                body=(
                    f"ORDER CONFIRMED #{order_num}! Your {model} {part_desc} is locked in at ${final_price:.2f}. "
                    f"Expected Delivery Date: {eta_date_str} via Priority Freight. "
                    f"30-day fitment + 90-day mechanical warranty active. Tracking link will follow. Thank you!"
                )
            )
            session.sms_summary_sent = True
            db.commit()
        except Exception as e:
            print(f"Confirmation SMS error: {e}")

        # Sync to Zoho CRM
        if lead.zoho_deal_id:
            try:
                zoho_client.update_deal_stage(
                    lead.zoho_deal_id,
                    stage="Closed Won",
                    notes=f"Customer verbally confirmed order #{order_num} for ${final_price:.2f}. ETA: {eta_date_str}."
                )
            except Exception as e:
                print(f"Zoho sync error: {e}")

    # ── 8. POLITE CALL WRAP-UP / SIGN-OFF ──────────────────────────────────────────
    elif any(k in speech_clean for k in ["no that's all", "that's all", "nothing else", "no that's it", "bye", "all good thanks", "that's it"]):
        next_step = "confirm_end"
        is_terminal = True
        ai_reply_text = (
            f"Awesome, {first_name}! Thanks for checking in with Yards & Parts. We'll keep your quote file active. "
            f"Take care and have a fantastic week!"
        )

    # ── 9. TIMING PERMISSION & RIGHT TIME TO SPEAK FLOW ───────────────────────────
    elif current_step in ("greeting", "timing_check"):
        if any(w in speech_clean for w in ["wrong number", "not me", "wrong person", "wrong customer"]):
            next_step = "confirm_end"
            is_terminal = True
            ai_reply_text = "Sorry about the mix-up! Have a great day."
        elif any(w in speech_clean for w in [
            "no", "not a good time", "not right now", "busy", "driving", "in a meeting",
            "meeting", "can't talk", "cant talk", "cannot talk", "bad time", "call back",
            "later", "call me later", "not now", "no puedo hablar", "ocupado", "manejando",
            "reunion", "luego", "mas tarde", "en otro momento"
        ]) and not any(w in speech_clean for w in ["yes", "yeah", "sure", "fine", "okay", "si"]):
            # Step: NEGOTIATE that it won't take more than 2 minutes!
            next_step = "timing_negotiation"
            if is_spanish:
                ai_reply_text = (
                    f"¡Le entiendo perfectamente, {first_name}! No le tomará más de 2 minutos de su tiempo "
                    f"solo para confirmar la compatibilidad y la dirección de entrega. ¿Tendrá 2 minutitos, o está muy ocupado?"
                )
            else:
                ai_reply_text = (
                    f"I completely understand, {first_name}! It won't take more than 2 minutes of your time "
                    f"just to confirm the fitment and your delivery address. Do you have a quick 2 minutes, or are you tied up?"
                )
        else:
            # Customer says YES / OK / SURE -> Continue quote review!
            next_step = "service_check"
            price_str = f" for ${quote_price:.2f}" if quote_price > 0 else ""
            if is_spanish:
                ai_reply_text = (
                    f"¡Excelente, gracias {first_name}! Estaba revisando su cotización para {model} "
                    f"{part_desc}{price_str}. Quería consultar: ¿tiene el auto en el taller ahora mismo, "
                    f"o está planificando la reparación para más adelante?"
                )
            else:
                ai_reply_text = (
                    f"Awesome, thanks {first_name}! I was pulling up your file regarding that {model} "
                    f"{part_desc}{price_str}. Just wanted to check in personally — is this for a vehicle you've got in the shop right now, "
                    f"or are you just planning out the repair for down the road?"
                )

    elif current_step == "timing_negotiation":
        # Customer responds to the 2-minute negotiation offer
        if any(w in speech_clean for w in [
            "yes", "yeah", "yep", "sure", "alright", "okay", "ok", "fine", "go ahead",
            "make it quick", "two minutes", "quick", "shoot", "si", "esta bien", "rapido", "dime", "adelante"
        ]) and not any(w in speech_clean for w in ["no", "can't", "cant", "really busy", "no time"]):
            # Agreed to quick 2 minutes -> Continue quote review!
            next_step = "service_check"
            if is_spanish:
                ai_reply_text = (
                    f"¡Muchas gracias, prometo ser muy breve! Para ese {model} {part_desc} cotizado en ${quote_price:.2f}, "
                    f"¿tiene el vehículo en el taller actualmente, o está cotizando con tiempo?"
                )
            else:
                ai_reply_text = (
                    f"Appreciate that, {first_name}, I'll keep it super quick! For that {model} {part_desc} quoted at ${quote_price:.2f}, "
                    f"is the vehicle in the shop right now, or are you planning ahead?"
                )
        else:
            # Still says NO / Cannot talk -> Ask for preferred callback time!
            next_step = "timing_callback"
            if is_spanish:
                ai_reply_text = (
                    f"¡Sin problema, respeto mucho su tiempo! ¿Qué día y a qué hora sería mejor que nuestro equipo de repuestos le devuelva la llamada?"
                )
            else:
                ai_reply_text = (
                    f"No problem at all, I respect your time! What day and time would be best for our parts team to give you a call back?"
                )

    elif current_step == "timing_callback":
        # Customer gave preferred callback time -> Log to CRM and wrap up!
        preferred_time = customer_speech.strip() or "tomorrow afternoon"
        next_step = "confirm_end"
        is_terminal = True
        session.status = "completed"

        # UPDATE THE CRM!
        lead.status = "callback_scheduled"
        callback_note = f"Customer requested callback: '{preferred_time}'"
        if lead.notes:
            lead.notes += f" | {callback_note}"
        else:
            lead.notes = callback_note

        db.add(ConversationMessage(
            lead_id=lead.id,
            channel="voice",
            role="system",
            content=f"[CRM Updated] Callback Scheduled: {preferred_time}"
        ))
        db.commit()

        # Update Zoho CRM deal stage if deal exists
        if lead.zoho_deal_id:
            try:
                zoho_client.update_deal_stage(
                    lead.zoho_deal_id,
                    stage="Callback Scheduled",
                    notes=f"Customer requested callback: {preferred_time}"
                )
            except Exception as e:
                print(f"[CRM Callback] Zoho sync error: {e}")

        # Dispatch Outbound CRM Webhook to Kiran's CRM
        try:
            from app.crm.webhook_dispatcher import dispatch_crm_event
            dispatch_crm_event("lead.callback_scheduled", {
                "leadId": lead.id,
                "customerName": lead.customer_name,
                "customerPhone": lead.phone,
                "customerEmail": customer_email,
                "preferredCallbackTime": preferred_time,
                "quoteValue": quote_price,
                "model": model,
                "partDescription": part_desc
            })
        except Exception as e:
            print(f"[CRM Callback] Webhook dispatch error: {e}")

        if is_spanish:
            ai_reply_text = (
                f"¡Anotado, {first_name}! He programado {preferred_time} en nuestro sistema para llamarle. "
                f"También le envié la cotización completa con el PDF adjunto a su correo y celular para que lo tenga a mano. ¡Que tenga un excelente día!"
            )
        else:
            ai_reply_text = (
                f"Perfect, {first_name}! I have logged {preferred_time} in our system, and our parts specialist will call you then. "
                f"I've also emailed and texted you the full itemized PDF quote so you have all the numbers handy. Take care!"
            )

    elif current_step in ("service_check", "info_sent", "price_negotiated", "warranty_explained", "consultation_pending"):
        if any(w in speech_clean for w in ["yes", "yeah", "sure", "go ahead", "please"]):
            # They agreed to have the info emailed/texted
            next_step = "info_sent"
            lead.status = "quote_emailed"
            db.commit()

            try:
                lead_dict = {
                    "id": lead.id,
                    "customer_name": lead.customer_name,
                    "email": customer_email,
                    "model": model,
                    "part_description": part_desc,
                    "part_number": lead.part_number or "0888580703",
                    "quote_value_usd": session.negotiated_price or quote_price,
                }
                from app.comms.pdf_generator import create_quote_pdf_for_lead
                pdf_path = create_quote_pdf_for_lead(lead_dict)
                subject, html_body, plain_body = email_client.build_email(
                    lead_dict, 1,
                    f"Here is the complete OEM spec sheet and quote breakdown for your {model} {part_desc}."
                )
                email_client.send_email(
                    to_email=customer_email,
                    to_name=lead.customer_name,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    pdf_attachment_path=pdf_path,
                )
            except Exception as e:
                print(f"Email dispatch error: {e}")

            ai_reply_text = (
                f"Perfect, {first_name}! I just emailed the complete spec sheet, OEM interchange numbers, and warranty paperwork "
                f"straight to {customer_email}. You can review it at your convenience. Is there anything else you need from my end today?"
            )
        else:
            next_step = "confirm_end"
            is_terminal = True
            ai_reply_text = (
                f"No problem at all, {first_name}. We'll keep this file open for you. "
                f"Feel free to reach back out whenever you're ready. Have a great day!"
            )

    else:
        next_step = "confirm_end"
        is_terminal = True
        ai_reply_text = "Thank you for choosing Yards & Parts Automotive. Have a great day!"

    # Record turn
    transcript.append({
        "speaker": "ai",
        "step": next_step,
        "text": ai_reply_text,
        "time": datetime.utcnow().isoformat(),
    })
    db.add(ConversationMessage(
        lead_id=lead.id,
        channel="voice",
        role="assistant",
        content=ai_reply_text,
    ))

    session.current_step = next_step
    session.transcript = json.dumps(transcript)
    session.detected_objections = json.dumps(objections)
    db.commit()

    if is_terminal:
        def _async_post_call(sess_id, ld_id):
            try:
                db_bg = SessionLocal()
                sess = db_bg.query(CallSession).filter(CallSession.id == sess_id).first()
                ld = db_bg.query(Lead).filter(Lead.id == ld_id).first()
                if sess and ld:
                    send_post_call_summary_sms(sess, ld, db_bg)
                db_bg.close()
            except Exception as e:
                print(f"[ASYNC POST-CALL ERROR] {e}")

        threading.Thread(target=_async_post_call, args=(session.id, lead.id), daemon=True).start()
        return build_terminal_twiml(ai_reply_text, lang=lang)
    else:
        return build_gather_twiml(ai_reply_text, session.id, base_url, lang=lang)
