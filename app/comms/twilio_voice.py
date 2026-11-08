"""
comms/twilio_voice.py
---------------------
Initiates outbound phone calls via Twilio.
Uses TwiML to play a spoken message (no live agent required for Touch 1).
For a live agent workflow, swap the TwiML URL for a <Dial> verb.
"""

import os
import re
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Say
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER  = os.getenv("TWILIO_PHONE_NUMBER")

# The public URL Twilio fetches to execute the interactive voice dialogue state machine
TWIML_BASE_URL = os.getenv("TWIML_BASE_URL", "https://homeland-ride-strain-explanation.trycloudflare.com")


def get_twiml_base_url() -> str:
    """Dynamically resolves the active public webhook URL from .env or environment."""
    try:
        from dotenv import dotenv_values
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        if os.path.exists(env_file):
            vals = dotenv_values(env_file)
            if vals.get("TWIML_BASE_URL"):
                return vals["TWIML_BASE_URL"].rstrip("/")
    except Exception:
        pass
    return os.getenv("TWIML_BASE_URL", "https://teams-rights-regions-config.trycloudflare.com").rstrip("/")


def sanitize_phone(phone: str) -> str:
    """Sanitizes phone number to E.164 format."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", phone.strip())
    if digits.startswith("+"):
        return digits
    elif len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


def make_call(to_number: str, lead_id: int, touch_number: int, call_script: str = None, language: str = "en-US", base_url: str = None) -> dict:
    """
    Initiate an interactive 2-way conversational outbound call.
    Twilio connects to /twiml/call-start/{session_id} to begin the state machine.
    Supports English (en-US) and Spanish (es-US).
    """
    effective_base_url = (base_url or get_twiml_base_url()).rstrip("/")
    from app.models.db import SessionLocal, CallSession, Lead

    db = SessionLocal()
    session = CallSession(
        lead_id=lead_id,
        current_step="greeting",
        status="in_progress",
        transcript="[]",
        detected_objections="[]",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session_id = session.id
    db.close()

    load_dotenv()
    client = Client(os.getenv("TWILIO_ACCOUNT_SID") or ACCOUNT_SID, os.getenv("TWILIO_AUTH_TOKEN") or AUTH_TOKEN)
    twiml_url = f"{effective_base_url}/twiml/call-start/{session_id}?lang={language}"

    try:
        call = client.calls.create(
            url=twiml_url,
            to=to_number,
            from_=os.getenv("TWILIO_PHONE_NUMBER") or FROM_NUMBER,
            status_callback=f"{effective_base_url}/webhook/voice-status/{session_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        return {
            "status":     "success",
            "sid":        call.sid,
            "call_status": call.status,
            "to":         call.to,
            "session_id": session_id,
            "language":   language,
        }
    except Exception as e:
        err_msg = str(e)
        print(f"Twilio Voice Call error for {to_number}: {err_msg}")
        if "unverified" in err_msg.lower():
            clean_msg = (
                f"Twilio Trial Restriction: {to_number} is unverified. "
                f"Twilio trial accounts can only place calls to verified caller IDs (e.g. +15550192834). "
                f"Please test with +15550192834 or add {to_number} to Verified Caller IDs in your Twilio Console."
            )
        else:
            clean_msg = f"Twilio Voice Error: {err_msg}"
        return {
            "status": "error",
            "error": clean_msg,
            "sid": None,
            "session_id": session_id,
            "language": language,
        }


def place_outbound_call(lead, db=None, base_url: str = None, language: str = "en-US") -> dict:
    """Helper to initiate an outbound call for a Lead model with language support."""
    clean_num = sanitize_phone(lead.phone)
    return make_call(to_number=clean_num, lead_id=lead.id, touch_number=1, language=language, base_url=base_url)


def build_twiml_script(call_script: str) -> str:
    """
    Convert a plain-text call script into a TwiML response string.
    Twilio reads this aloud using text-to-speech.

    Args:
        call_script: the spoken script text

    Returns:
        TwiML XML string
    """
    response = VoiceResponse()
    response.say(call_script, voice="Polly.Matthew", language="en-IN")
    # Pause then prompt for keypress
    response.say(
        "Press 1 to speak with our sales team now, "
        "or press 2 to receive a text message with more details.",
        voice="Polly.Matthew",
        language="en-IN",
    )
    return str(response)
