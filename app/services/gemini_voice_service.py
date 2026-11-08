"""
app/services/gemini_voice_service.py
------------------------------------
Dynamic AI reasoning engine powered by Google's Gemini Flash-Lite model.
Enables natural, multi-turn voice phone conversations within strict
commercial order boundaries, fitment guarantees, and pricing safeguards.
"""

import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-flash-lite-latest"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def get_gemini_api_key() -> str:
    """Dynamically reads the Gemini API key from environment or .env."""
    load_dotenv()
    return os.getenv("GEMINI_API_KEY", "").strip()


def build_system_instruction(lead_data: dict, current_step: str = "") -> str:
    """
    Constructs a hardened system prompt that confines Gemini's reasoning
    strictly within the vehicle and quote boundaries.
    """
    customer_name = lead_data.get("customer_name") or "there"
    first_name = customer_name.split()[0]
    model = lead_data.get("model") or "your vehicle"
    part_desc = lead_data.get("part_description") or "the mechanical assembly"
    quote_price = float(lead_data.get("quote_value_usd") or 0.0)
    discount_price = round(quote_price * 0.96, 2)  # Exactly 4% trade discount
    discount_amount = round(quote_price * 0.04, 2)

    return f"""You are Alex, an expert, warm, and professional B2B automotive sales representative for Yards & Parts Automotive on a live voice phone call.
You are speaking directly with {first_name} regarding their quote for a {model} {part_desc}.

COMMERCIAL & ORDER BOUNDARIES (STRICT COMPLIANCE REQUIRED):
1. Quoted Price: Original quote is ${quote_price:.2f}.
2. Pre-Authorized Trade Discount: You are authorized to offer our commercial fleet trade discount of up to 4% off (${discount_amount:.2f} savings), bringing the final price to ${discount_price:.2f}. You CANNOT and MUST NEVER offer more than 4% under any circumstances, to protect our gross margin and warranty reserves.
3. Logistics & Freight: Includes free express priority freight with pallet dispatch within 24 hours and direct carrier tracking.
4. Sourcing & Quality: Sourced strictly under 80,000 certified miles/kilometres with full vehicle inspection history.
5. Bench Testing: 4-point hydraulic bench testing verified at 180 PSI compression before loading.
6. Dual Warranty: 30-day direct fitment guarantee (ensures exact bolt-up) plus full 90-day mechanical replacement warranty on all internal components.
7. Return Policy: If any fitment defect or freight damage occurs, we provide immediate exchange or full refund with prepaid return freight.
8. Current State: {current_step}.

CRITICAL RULES FOR SPOKEN VOICE PHONE CALLS:
- Keep every response concise: strictly 1 to 2 spoken sentences (under 35 words total).
- Speak naturally, warmly, and conversationally as if talking on a phone line.
- NEVER use markdown, bullet points, asterisks, quotation marks, or robotic text.
- If the customer speaks Spanish, respond naturally in fluent Spanish (es-US).
- If the customer agrees to proceed or buy ("let's do it", "place order", "go ahead and order", "buy it", "confirm"), enthusiastically confirm their order at the locked-in price and let them know the receipt and tracking have been dispatched.
- Never make up fake part numbers or contradict the 4% discount limit.
"""


def generate_voice_response(
    customer_speech: str,
    lead_data: dict,
    transcript_history: list = None,
    current_step: str = "",
    timeout: float = 3.0
) -> dict:
    """
    Calls Gemini Flash-Lite to reason and generate a natural spoken reply.
    Returns:
        {
            "reply": str,
            "order_confirmed": bool,
            "discount_granted": bool,
            "source": "gemini" | "fallback"
        }
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return {"reply": None, "order_confirmed": False, "discount_granted": False, "source": "no_key"}

    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    url = f"{GEMINI_ENDPOINT.format(model=model_name)}?key={api_key}"

    system_instruction = build_system_instruction(lead_data, current_step)

    # Build multi-turn conversational contents
    contents = []
    if transcript_history:
        # Include up to the last 6 turns for conversational context
        for turn in transcript_history[-6:]:
            role = "user" if turn.get("speaker") == "customer" else "model"
            text = turn.get("text", "").strip()
            if text:
                contents.append({
                    "role": role,
                    "parts": [{"text": text}]
                })

    # Add latest customer turn
    contents.append({
        "role": "user",
        "parts": [{"text": customer_speech}]
    })

    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 90,
            "temperature": 0.35,
            "topP": 0.95
        }
    }

    try:
        res = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        if res.status_code == 200:
            data = res.json()
            candidates = data.get("candidates", [])
            if candidates:
                raw_text = candidates[0]["content"]["parts"][0]["text"].strip()
                # Clean any stray formatting or markdown asterisks
                clean_reply = re.sub(r"[\*\_#`]", "", raw_text).strip()

                # Detect if order was confirmed in speech
                speech_lower = customer_speech.lower()
                order_confirmed = any(k in speech_lower for k in [
                    "place the order", "place order", "go ahead and order", "confirm the order",
                    "confirm order", "lock in the order", "buy it", "charge it", "order it",
                    "let's do it", "lets do it", "go ahead"
                ]) and not any(k in speech_lower for k in ["no", "wait", "can't", "cant", "don't"])

                discount_granted = any(k in speech_lower for k in [
                    "discount", "lower", "better price", "deal", "bring it down", "can you do better"
                ])

                return {
                    "reply": clean_reply,
                    "order_confirmed": order_confirmed,
                    "discount_granted": discount_granted,
                    "source": "gemini"
                }
    except Exception as e:
        print(f"[Gemini Voice Service] API request error: {e}")

    return {"reply": None, "order_confirmed": False, "discount_granted": False, "source": "fallback"}
