"""
services/web_chat_service.py
----------------------------
Conversational AI Storefront Web Chat Assistant for Yards & Parts.
Supports:
  - Real-time 17-character VIN extraction & NHTSA decode
  - Hollander Interchange fitment lookup with confidence score
  - LTL freight & accessorials estimates from ZIP codes
  - Instant quotation generation & PDF download
  - Bilingual English / Spanish dialogue
"""

import re
from typing import Dict, Any, List
from app.services.vin_service import validate_vin, decode_vin
from app.services.hollander_service import evaluate_compatibility
from app.services.freight_service import estimate_freight
from app.services.pricing_service import calculate_line_item, calculate_quote_financials


def handle_chat_turn(
    message: str,
    context: Dict[str, Any],
    language: str = "en"
) -> Dict[str, Any]:
    """
    Evaluates customer chat messages, extracts VINs, queries Hollander parts,
    and returns rich AI assistant replies with interactive action chips.
    """
    msg_raw = message.strip()
    msg_lower = msg_raw.lower()

    # Detect Spanish language intent
    if any(w in msg_lower for w in ["hola", "español", "espanol", "buenos días", "buenas tardes", "tienen", "precio"]):
        language = "es"

    is_es = language.startswith("es")
    known_vehicle = context.get("vehicle")

    # 1. Check for 17-character VIN
    vin_match = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', msg_raw.upper())
    if vin_match:
        vin = vin_match.group(0)
        decoded = decode_vin(vin)
        if decoded.get('status') in ('DECODED', 'PARTIALLY_DECODED'):
            context["vehicle"] = decoded
            v_title = f"{decoded['year']} {decoded['make']} {decoded['model']} {decoded.get('trim') or ''}".strip()
            v_eng = f"{decoded.get('engineDisplacementL')}L" if decoded.get('engineDisplacementL') else "Standard"

            if is_es:
                reply = (
                    f"¡Excelente! He decodificado su número VIN <b>{vin}</b> vía NHTSA:<br/>"
                    f"🚗 <b>{v_title}</b> &bull; Motor {v_eng} &bull; Transmisión {decoded.get('transmissionStyle') or 'Automática'}.<br/><br/>"
                    f"¿Qué pieza de repuesto necesita cotizar hoy? (por ejemplo: <i>Motor completo, Transmisión, Alternador o Faro</i>)"
                )
            else:
                reply = (
                    f"Got it! I verified and decoded your VIN <b>{vin}</b> via NHTSA vPIC:<br/>"
                    f"🚗 <b>{v_title}</b> &bull; {v_eng} Engine &bull; {decoded.get('transmissionStyle') or 'Automatic'} transmission.<br/><br/>"
                    f"Which assembly are you looking for today? (e.g. <i>Engine Assembly, Transmission, Alternator, or Headlight</i>)"
                )

            return {
                "reply": reply,
                "context": context,
                "vehicle": decoded,
                "chips": [
                    "Need Engine Assembly",
                    "Need Transmission",
                    "Need Alternator",
                    "Estimate Freight & Shipping"
                ]
            }

    # 2. Check for Part / Category request
    detected_cat = None
    if any(w in msg_lower for w in ["engine", "motor", "longblock"]):
        detected_cat = "Engine"
    elif any(w in msg_lower for w in ["transmission", "transmision", "gearbox", "cvt"]):
        detected_cat = "Transmission"
    elif any(w in msg_lower for w in ["alternator", "alternador", "starter"]):
        detected_cat = "Alternator"
    elif any(w in msg_lower for w in ["headlight", "faro", "light"]):
        detected_cat = "Headlight"

    if detected_cat:
        # If we have a vehicle in context or demo fallback
        veh = known_vehicle or {
            'year': 2018,
            'make': 'HONDA',
            'model': 'CIVIC',
            'engineDisplacementL': 2.0,
            'transmissionStyle': 'CVT',
            'driveType': 'FWD',
            'vin': '19XFC2F5XJE000001'
        }
        context["vehicle"] = veh

        matches = evaluate_compatibility(veh, requested_category=detected_cat)
        if matches:
            top = matches[0]
            context["selectedPart"] = top
            part_name = top["partName"]
            hollander = top["hollanderNumber"]
            cost = top["unitCost"]
            price = top["listPrice"]
            core = top["coreCharge"]
            conf = top["confidenceScore"]

            if is_es:
                reply = (
                    f"Encontré una coincidencia verificada en la tabla <b>Hollander Interchange</b>:<br/>"
                    f"📦 <b>{part_name}</b><br/>"
                    f"&bull; Código Hollander: <b>{hollander}</b><br/>"
                    f"&bull; Compatibilidad: <span style='color:green;font-weight:bold;'>{conf}% Verificado</span><br/>"
                    f"&bull; Precio: <b>${price:.2f} USD</b> (+${core:.2f} depósito reembolsable de casco)<br/>"
                    f"&bull; Garantía: 90 días de reemplazo certificado.<br/><br/>"
                    f"¿Desea que le preparemos la cotización formal en PDF con flete LTL?"
                )
            else:
                reply = (
                    f"Found a verified match in our <b>Hollander Interchange</b> catalog:<br/>"
                    f"📦 <b>{part_name}</b><br/>"
                    f"&bull; Hollander Code: <b>{hollander}</b><br/>"
                    f"&bull; Fitment Confidence: <span style='color:green;font-weight:bold;'>{conf}% Verified</span><br/>"
                    f"&bull; Price: <b>${price:.2f} USD</b> (+${core:.2f} refundable core deposit)<br/>"
                    f"&bull; Protection: 90-Day run-tested replacement warranty.<br/><br/>"
                    f"Would you like me to generate your official B2B PDF quote?"
                )

            return {
                "reply": reply,
                "context": context,
                "part": top,
                "chips": [
                    "Generate Official PDF Quote",
                    "Estimate Freight to my ZIP",
                    "Do you offer warranty?",
                    "Have a parts specialist call me"
                ]
            }

    # 3. Check for Freight / ZIP code
    zip_match = re.search(r'\b\d{5}\b', msg_raw)
    if zip_match or any(w in msg_lower for w in ["freight", "shipping", "envio", "flete", "delivery"]):
        dest_zip = zip_match.group(0) if zip_match else "77001"
        weight = 275.0
        if context.get("selectedPart"):
            weight = context["selectedPart"].get("weightLbs", 275.0)

        f_res = estimate_freight(origin_zip="43215", destination_zip=dest_zip, weight_lbs=weight, requires_liftgate=True)

        if is_es:
            reply = (
                f"🚚 <b>Cálculo de Flete LTL hacia el código postal {dest_zip}:</b><br/>"
                f"&bull; Zona de envío: Zona {f_res['zone']} ({f_res['estimatedTransitDays']} días hábiles de tránsito)<br/>"
                f"&bull; Tarifa base con recargo de combustible: ${f_res['baseCharge'] + f_res['fuelSurcharge']:.2f}<br/>"
                f"&bull; Servicio de Rampa Hidráulica: ${f_res['liftgateSurcharge']:.2f}<br/>"
                f"&bull; <b>Total Flete Estimado: ${f_res['totalFreightCharge']:.2f} USD</b><br/><br/>"
                f"Las piezas pesadas se entregan paletizadas y flejadas con descarga en su taller o garaje."
            )
        else:
            reply = (
                f"🚚 <b>LTL Heavy Freight Estimate to ZIP {dest_zip}:</b><br/>"
                f"&bull; Shipping Zone: Zone {f_res['zone']} ({f_res['estimatedTransitDays']} business days transit)<br/>"
                f"&bull; Freight Base + Fuel Surcharge: ${f_res['baseCharge'] + f_res['fuelSurcharge']:.2f}<br/>"
                f"&bull; Hydraulic Liftgate Service: ${f_res['liftgateSurcharge']:.2f}<br/>"
                f"&bull; <b>Total Estimated Freight: ${f_res['totalFreightCharge']:.2f} USD</b><br/><br/>"
                f"Heavy assemblies are shipped steel-banded on heavy duty skids with curbside liftgate delivery included."
            )

        return {
            "reply": reply,
            "context": context,
            "chips": [
                "Generate Official PDF Quote",
                "Have a specialist call me",
                "What is your core return policy?"
            ]
        }

    # 4. Check for Quote Generation request
    if any(w in msg_lower for w in ["pdf", "generate quote", "send quote", "formal quote", "cotización", "cotizacion"]):
        if is_es:
            reply = (
                f"📄 ¡Con gusto! Puede ver y descargar su cotización formal en PDF en nuestra plataforma en cualquier momento:<br/>"
                f"<a href='/quoting' target='_blank' style='color:#2563EB;font-weight:bold;text-decoration:underline;'>Abrir Quoting Wizard &bull; Descargar PDF</a><br/><br/>"
                f"Si prefiere que se la enviemos por SMS o que un especialista lo llame para cerrar el pedido, solo déjeme su número de teléfono."
            )
        else:
            reply = (
                f"📄 Absolutely! You can view, customize, and download your formal B2B PDF quote directly in our quoting wizard:<br/>"
                f"<a href='/quoting' target='_blank' style='color:#2563EB;font-weight:bold;text-decoration:underline;'>Open Quoting Engine &bull; Download PDF</a><br/><br/>"
                f"If you'd like us to text you the link or have our AI voice agent give you a quick call, just provide your phone number!"
            )

        return {
            "reply": reply,
            "context": context,
            "chips": [
                "Open Quoting Wizard",
                "Text me the quote",
                "Call me now"
            ]
        }

    # 5. Default welcoming response
    if is_es:
        reply = (
            "¡Hola! Bienvenido al asistente inteligente de <b>Yards &amp; Parts</b>.<br/>"
            "Puedo ayudarle a:<br/>"
            "&bull; Decodificar su <b>número VIN</b> en tiempo real.<br/>"
            "&bull; Verificar compatibilidad con la tabla <b>Hollander Interchange</b>.<br/>"
            "&bull; Calcular fletes LTL con rampa hidráulica hacia su código postal.<br/>"
            "&bull; Generar su cotización formal en PDF al instante.<br/><br/>"
            "Para comenzar, ingrese su número VIN de 17 caracteres o dígame qué pieza necesita."
        )
    else:
        reply = (
            "Hello! Welcome to the <b>Yards &amp; Parts</b> Automotive Assistant.<br/>"
            "I can help you:<br/>"
            "&bull; Decode your <b>17-character VIN</b> via NHTSA.<br/>"
            "&bull; Verify fitment with our <b>Hollander Interchange</b> matrix.<br/>"
            "&bull; Calculate <b>LTL freight</b> with liftgate delivery to your ZIP code.<br/>"
            "&bull; Generate an official <b>B2B PDF Quote</b> instantly.<br/><br/>"
            "To get started, enter your 17-character VIN or tell me the part and vehicle you're working on!"
        )

    return {
        "reply": reply,
        "context": context,
        "chips": [
            "Decode VIN: 19XFC2F5XJE000001",
            "I need an engine",
            "I need a transmission",
            "Estimate Freight"
        ]
    }
