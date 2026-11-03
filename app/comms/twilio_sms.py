"""
comms/twilio_sms.py
-------------------
Sends SMS messages via Twilio.
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER  = os.getenv("TWILIO_PHONE_NUMBER")


def send_sms(to_number: str = None, body: str = "", to_phone: str = None) -> dict:
    target_number = to_number or to_phone
    if not target_number:
        return {"status": "error", "error": "No recipient phone number provided"}
    """
    Send an SMS to a customer.

    Args:
        to_number: E.164 format, e.g. '+919876543210'
        body:      Message text (keep under 320 chars for best deliverability)

    Returns:
        dict with 'sid', 'status', 'to'
    """
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    try:
        message = client.messages.create(
            body=body,
            from_=FROM_NUMBER,
            to=target_number,
        )
        return {
            "status": "sent",
            "sid":    message.sid,
            "to":     message.to,
        }
    except Exception as e:
        err_msg = str(e)
        print(f"Twilio SMS error for {target_number}: {err_msg}")
        if "unverified" in err_msg.lower():
            clean_msg = (
                f"Twilio Trial Restriction: {target_number} is unverified. "
                f"Twilio trial accounts can only send SMS to verified caller IDs (e.g. +15550192834). "
                f"Please test with +15550192834 or add {target_number} to Verified Caller IDs in your Twilio Console."
            )
        else:
            clean_msg = f"Twilio SMS Error: {err_msg}"
        return {
            "status": "error",
            "error": clean_msg,
            "sid": None,
        }


def build_sms_body(lead: dict, touch_number: int, battlecard_text: str, lang: str = "en") -> str:
    """
    Build an SMS message body for a given touch number (English or Spanish).

    Args:
        lead:           dict with customer_name, model, part_description
        touch_number:   1, 2, or 3
        battlecard_text: pre-fetched battlecard snippet
        lang:           language code ('en' or 'es')
    """
    name  = lead.get("customer_name", "there").split()[0]   # first name only
    model = lead.get("model", "your vehicle")
    part  = lead.get("part_description", "the part")
    is_es = str(lang).lower().startswith("es") or lead.get("preferred_language") == "es"

    if is_es:
        intros = {
            1: f"Hola {name}, de Yards & Parts Automotive. Recientemente cotizó {part} para su {model}.",
            2: f"Hola {name}, dándole seguimiento a su cotización de {part} para su {model}.",
            3: f"Hola {name}, último aviso sobre el repuesto {part} cotizado para su {model}.",
        }
        intro = intros.get(touch_number, intros[1])
        cta   = " Responda SI para proceder. Responda ALTO para cancelar."
    else:
        intros = {
            1: f"Hi {name}, this is Yards & Parts Automotive. You recently got a quote on {part} for your {model}.",
            2: f"Hi {name}, just following up on your {model} {part} quote.",
            3: f"Hi {name}, last check-in on the {part} you quoted for your {model}.",
        }
        intro = intros.get(touch_number, intros[1])
        cta   = " Reply YES to proceed or call us back. Reply STOP to unsubscribe."

    return f"{intro} {battlecard_text}{cta}"

    body = f"{intro} {battlecard_text}{cta}"

    # Truncate to 320 chars just in case
    if len(body) > 320:
        body = body[:317] + "..."

    return body
