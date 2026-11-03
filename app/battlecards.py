"""
battlecards.py
--------------
Objection detection and battlecard script library.
Matches inbound keywords from a customer to a pre-written response script.
These scripts are injected into SMS, email, and call scripts automatically.
"""

from typing import Optional
import re

# ── Battlecard definitions ────────────────────────────────────────────────────
# Each entry has:
#   label            : human readable name
#   subtitle         : badge or key highlight
#   trigger_keywords : regex pattern to detect the objection type
#   description      : core standard operating policy
#   sms_snippet      : short version for SMS (160 chars max)
#   email_paragraph  : full paragraph for email body
#   call_script      : spoken script for a phone agent or IVR

BATTLECARDS = {
    "mileage_concern": {
        "label": "Mileage Concern — Verified <80k km",
        "subtitle": "Verified <80k km",
        "icon": "🔧",
        "description": "All engine and transmission units sourced under 80,000 km with full vehicle inspection logs attached.",
        "trigger_keywords": r"mileage|miles|high km|worn|how many miles|kilometres|kilometers|old engine|how old|age|used",
        "sms_snippet": (
            "All engine and transmission units are sourced under 80,000 km with full vehicle inspection logs attached. "
            "Happy to text you the inspection certificate!"
        ),
        "email_paragraph": (
            "We completely understand mileage is a top priority when sourcing replacement components. "
            "Here is our standard quality protocol:\n\n"
            "- All engine and transmission units are strictly sourced under 80,000 km.\n"
            "- Full vehicle inspection logs and odometer documentation are attached to every unit.\n"
            "- Units that do not meet factory OEM tolerances are never listed or shipped.\n\n"
            "Would you like us to email through the certified inspection logs for the specific unit in stock for your {model}?"
        ),
        "call_script": (
            "I completely understand your concern regarding mileage. Every engine and transmission unit we supply is "
            "strictly sourced under 80,000 kilometres with complete vehicle inspection logs attached. We can send you "
            "the odometer records directly before warehouse dispatch. Would that give you total confidence?"
        ),
    },

    "compression_testing": {
        "label": "Compression Testing — 4-Point Bench",
        "subtitle": "4-Point Bench",
        "icon": "🔩",
        "description": "Certified 4-point hydraulic bench test certificate sent prior to warehouse dispatch.",
        "trigger_keywords": r"compression|bench test|psi|cylinder pressure|leak down|tested|bench-tested",
        "sms_snippet": (
            "Every assembly passes a certified 4-point hydraulic bench test. "
            "We text you the certified pressure certificate before dispatch!"
        ),
        "email_paragraph": (
            "Mechanical integrity is non-negotiable for our engineering team. Before any unit leaves our warehouse:\n\n"
            "- A certified 4-point hydraulic bench and compression test is conducted across all cylinders.\n"
            "- A signed diagnostic test certificate is sent to you for your technician's review.\n"
            "- If any pressure reading falls outside factory spec, the part is rejected. Zero surprises.\n\n"
            "We are happy to attach the bench test paperwork for your {model} quote."
        ),
        "call_script": (
            "Great question on mechanical testing. Every single unit goes through a certified 4-point hydraulic bench test "
            "prior to warehouse dispatch. We actually send the signed pressure readings directly to you and your mechanic so you "
            "have 100% peace of mind before it is loaded onto the truck."
        ),
    },

    "freight_timelines": {
        "label": "Freight Timelines — 24h Dispatch",
        "subtitle": "24h Dispatch",
        "icon": "🚚",
        "description": "24-hour dispatch. Metro delivery within 3–5 business days with direct carrier tracking link.",
        "trigger_keywords": r"shipping|freight|delivery|how long|dispatch|arrive|carrier|tracking|transit",
        "sms_snippet": (
            "24-hour dispatch guaranteed. Metro delivery takes 3-5 business days with live direct carrier tracking links."
        ),
        "email_paragraph": (
            "We prioritize quick turnaround so your vehicle isn't stuck on the hoist:\n\n"
            "- **Dispatch Time:** In-stock orders are packed and dispatched within 24 hours.\n"
            "- **Transit Time:** Metro delivery takes 3–5 business days via insured road freight.\n"
            "- **Live Tracking:** Direct carrier tracking links and consignment numbers are texted and emailed upon loading.\n\n"
            "We can reserve your delivery slot immediately."
        ),
        "call_script": (
            "We know workshop turnaround is critical. We dispatch all confirmed units within twenty-four hours. "
            "Metro delivery arrives within three to five business days, and you will get a direct carrier tracking link "
            "sent straight to your mobile the moment it leaves our loading dock."
        ),
    },

    "warranty_fitment": {
        "label": "Warranty & Fitment — 30d + 90d",
        "subtitle": "30d + 90d",
        "icon": "🛡️",
        "description": "30-day fitment guarantee + 90-day mechanical replacement warranty.",
        "trigger_keywords": r"warranty|guarantee|fitment|what if|break|fail|faulty|replacement",
        "sms_snippet": (
            "All parts backed by our 30-day fitment guarantee + 90-day mechanical replacement warranty. Zero hassle."
        ),
        "email_paragraph": (
            "You are fully protected from day one under our dual-tier warranty policy:\n\n"
            "- **30-Day Fitment Guarantee:** If the unit does not bolt in seamlessly or match OEM specifications, we exchange it or refund immediately.\n"
            "- **90-Day Mechanical Warranty:** Full parts replacement coverage on internal mechanical components.\n\n"
            "No lengthy claims processes or hidden exclusions."
        ),
        "call_script": (
            "We back all our Yards & Parts inventory with a dual protection plan: you get a thirty-day fitment guarantee "
            "to ensure it bolts up with your workshop, plus a full ninety-day mechanical replacement warranty. "
            "If there is any issue, we exchange it immediately at our cost."
        ),
    },

    "part_compatibility": {
        "label": "Part Compatibility — VIN Verified",
        "subtitle": "VIN Verified",
        "icon": "📋",
        "description": "Vehicle compatibility verified using the VIN, year, make, model, and engine specifications before quoting.",
        "trigger_keywords": r"vin|compatible|compatibility|fit|match|chassis|engine code|transmission code",
        "sms_snippet": (
            "100% VIN-verified compatibility. We cross-reference your 17-digit chassis number against official OEM EPC schematics."
        ),
        "email_paragraph": (
            "We eliminate fitment errors before the part leaves our facility:\n\n"
            "- Vehicle compatibility is verified using your 17-digit VIN, year, model, trim, and engine code.\n"
            "- We cross-reference the exact OEM Electronic Parts Catalog (EPC) schematics.\n"
            "- If you have your VIN handy, we can verify exact build date and revision code in seconds.\n\n"
            "Send us your VIN and our technical team will certify 100% fitment."
        ),
        "call_script": (
            "Fitment accuracy is our top priority. We verify vehicle compatibility directly against the 17-digit VIN, "
            "model year, and engine specification before dispatch, ensuring exact factory match with zero modifications needed."
        ),
    },

    "product_transparency": {
        "label": "Product Transparency — Actual Unit Photos",
        "subtitle": "Actual Unit Photos",
        "icon": "📸",
        "description": "Actual product photos available on request to verify the unit's condition, configuration, and visible identification numbers.",
        "trigger_keywords": r"photo|photos|picture|pictures|image|images|look like|condition|see it",
        "sms_snippet": (
            "Actual unit photos available on request! We can text high-res photos of the exact part and stamped serial numbers."
        ),
        "email_paragraph": (
            "We believe in total transparency when ordering parts:\n\n"
            "- Actual high-resolution photos of the specific unit in stock are available upon request.\n"
            "- Photos show physical condition, mounting brackets, harness connectors, and stamped OEM serial numbers.\n"
            "- You review the exact physical unit that will be packed onto your pallet before shipping.\n\n"
            "Would you like us to email photos of the available unit for your {model}?"
        ),
        "call_script": (
            "We believe in complete transparency. We have actual high-resolution photos of the exact unit in our warehouse "
            "showing mounting tabs, wiring harnesses, and stamped OEM serial numbers. I can text or email those photos "
            "directly to you right now if you want to inspect it yourself."
        ),
    },

    "competitive_pricing": {
        "label": "Competitive Pricing — Value First",
        "subtitle": "Value First",
        "icon": "💰",
        "description": "Transparent pricing with part cost and freight charges clearly itemized. Alternative options offered when available.",
        "trigger_keywords": r"price|expensive|cheaper|discount|budget|cost|deal|lower|reduce|quote value|too high",
        "sms_snippet": (
            "Transparent pricing: itemized part cost & freight charges. 4% trade discount available upon negotiation!"
        ),
        "email_paragraph": (
            "We maintain transparent, fair market pricing for every client:\n\n"
            "- Clear itemization: Part cost and insured freight charges are distinctly itemized.\n"
            "- Trade pricing: For workshops and active repairs, our 4% commercial trade discount is applied upon negotiation.\n"
            "- Alternative tiers: When available, we provide OEM new, certified reconditioned, and OEM interchange alternatives.\n\n"
            "We make sure the numbers work for your repair budget."
        ),
        "call_script": (
            "I completely respect your budget. Our pricing is completely transparent with itemized part and freight costs. "
            "For this quote, I can apply our negotiated 4% commercial trade discount right now and include complimentary express shipping "
            "to make the numbers work seamlessly for you."
        ),
    },

    "inventory_availability": {
        "label": "Inventory Availability — Stock Confirmed",
        "subtitle": "Stock Confirmed",
        "icon": "📦",
        "description": "Stock availability and warehouse location confirmed before payment or order commitment.",
        "trigger_keywords": r"stock|available|in stock|on shelf|warehouse|inventory|have it",
        "sms_snippet": (
            "Physical stock confirmed on the shelf in our warehouse. Ready for same-day allocation upon order."
        ),
        "email_paragraph": (
            "We never list ghost inventory:\n\n"
            "- Stock availability and warehouse shelf location are physically confirmed before accepting payment.\n"
            "- Units are placed on reserve for 24 hours under your quote number.\n"
            "- Immediate warehouse allocation upon confirmation ensures zero backorders or dispatch delays.\n\n"
            "Your {model} unit is currently staged and ready for shipment."
        ),
        "call_script": (
            "I have your part physically verified on our warehouse shelf right now. We confirm stock and bay location "
            "before any order commitment so you are never stuck on backorder. We can hold this unit for twenty-four hours under your name."
        ),
    },

    "returns_replacements": {
        "label": "Returns & Replacements — Clear Process",
        "subtitle": "Clear Process",
        "icon": "🔄",
        "description": "Clear return and replacement procedures communicated upfront, subject to the applicable warranty and return policy.",
        "trigger_keywords": r"return|returns|replace|replacement|refund|exchange|wrong part",
        "sms_snippet": (
            "Clear, hassle-free returns. Prepaid return freight provided if an item arrives incorrect or defective."
        ),
        "email_paragraph": (
            "We provide clear and simple return protocols:\n\n"
            "- Upfront transparency: Return and exchange steps are communicated clearly before payment.\n"
            "- Fast turn: If a replacement is needed, an exchange unit is expedited immediately.\n"
            "- Return authorization is handled seamlessly through our customer dispatch desk.\n\n"
            "You are covered with zero hidden restocking surprises."
        ),
        "call_script": (
            "We keep our return policy completely straightforward. If anything arrives damaged or does not fit as specified, "
            "our dispatch team issues an immediate replacement or refund under our thirty-day fitment policy. No red tape."
        ),
    },

    "order_updates": {
        "label": "Order Updates — Proactive Communication",
        "subtitle": "Proactive Communication",
        "icon": "📞",
        "description": "Customers receive updates on order confirmation, dispatch, tracking, and any unexpected delivery delays.",
        "trigger_keywords": r"update|updates|status|tracking|notification|sms update|progress",
        "sms_snippet": (
            "Proactive SMS and email updates at every stage: confirmation, packaging, dispatch, and estimated delivery."
        ),
        "email_paragraph": (
            "You will never have to wonder where your shipment is:\n\n"
            "- **Confirmation:** Instant digital receipt and order milestone link.\n"
            "- **Dispatch Notification:** Live carrier tracking link sent the moment the crate is scanned onto the truck.\n"
            "- **Milestone Alerts:** Proactive SMS alerts regarding estimated delivery arrival dates and driver updates.\n\n"
            "Our dispatch desk monitors your shipment until it is safely delivered."
        ),
        "call_script": (
            "You will receive proactive SMS and email updates at every stage: from order confirmation, to warehouse packing, "
            "to freight dispatch, complete with direct live tracking links so you are always informed."
        ),
    },

    "part_number_matching": {
        "label": "Part Number Matching — Cross-Reference Check",
        "subtitle": "Cross-Reference Check",
        "icon": "🎯",
        "description": "OEM and interchange part numbers cross-checked against available catalog data to reduce incorrect-part orders.",
        "trigger_keywords": r"part number|oem number|cross reference|interchange|superseded|pn|code",
        "sms_snippet": (
            "OEM and interchange numbers cross-checked across verified catalog inventory to eliminate incorrect orders."
        ),
        "email_paragraph": (
            "Precision part matching ensures accurate first-time installation:\n\n"
            "- OEM part numbers, superseded numbers, and aftermarket interchanges are cross-checked across catalog data.\n"
            "- We verify casting stamps and sensor harness revisions.\n"
            "- This systematic cross-reference eliminates incorrect-part deliveries and costly downtime.\n\n"
            "We have verified the OEM cross-reference for your {model} {part_description}."
        ),
        "call_script": (
            "Our parts specialists cross-reference OEM part numbers and superseded manufacturer codes against "
            "our master catalog data. That ensures you receive the exact right part number the very first time without trial-and-error."
        ),
    },

    "quote_followup": {
        "label": "Quote Follow-Up — No-Pressure Support",
        "subtitle": "No-Pressure Support",
        "icon": "🤝",
        "description": "Follow up on pending quotes, answer technical questions, and provide suitable alternatives without pressuring the customer.",
        "trigger_keywords": r"pressure|salesy|pushy|follow up|consult|questions|advice|options",
        "sms_snippet": (
            "No-pressure parts support. We answer technical questions, explain options, and help you find the right fit."
        ),
        "email_paragraph": (
            "Our philosophy is trusted consultation, never high-pressure sales:\n\n"
            "- We follow up on pending quotes to provide technical specs and answer installation questions.\n"
            "- We provide suitable alternatives if our standard option does not align with your repair plan.\n"
            "- We keep your quote file active and hold pricing steady without obligation.\n\n"
            "Reach out whenever you are ready — we are here to support your build."
        ),
        "call_script": (
            "Our role is simply to provide honest technical guidance and specs without any pressure. "
            "Whether you need technical measurements, wiring pinouts, or alternative parts, we are here to help whenever you are ready."
        ),
    },

    "trusted_experience": {
        "label": "Trusted Industry Experience — 25 Years | 1 Lakh+ Happy Customers",
        "subtitle": "25 Years | 1L+ Customers",
        "icon": "🏆",
        "description": "Backed by 25 years of industry experience and the trust of over 100,000 satisfied customers, delivering reliable automotive parts and customer-focused service.",
        "trigger_keywords": r"reputation|experience|trust|reviews|who are you|how long|credible|reliable dealer",
        "sms_snippet": (
            "Backed by 25 years of industry experience and over 100,000 satisfied customers across leading automotive models."
        ),
        "email_paragraph": (
            "You are in experienced, reputable hands:\n\n"
            "- **25 Years in Automotive Parts:** Decades of specialized driveline, engine, and mechanical component expertise.\n"
            "- **100,000+ Satisfied Customers:** Trusted by leading independent mechanics, commercial fleets, and retail owners.\n"
            "- **Dedicated Support:** Direct phone and email access to certified automotive specialists from quote to installation.\n\n"
            "Thank you for trusting Yards & Parts Automotive."
        ),
        "call_script": (
            "We are backed by over twenty-five years of dedicated automotive industry experience and the trust of more than "
            "one hundred thousand satisfied customers. You are dealing with experienced specialists who stand behind every single part we dispatch."
        ),
    },
}

# Aliases for backward compatibility
BATTLECARDS["mileage_compression"] = BATTLECARDS["mileage_concern"]
BATTLECARDS["mileage"] = BATTLECARDS["mileage_concern"]
BATTLECARDS["compression"] = BATTLECARDS["compression_testing"]
BATTLECARDS["freight_warranty"] = BATTLECARDS["freight_timelines"]
BATTLECARDS["warranty"] = BATTLECARDS["warranty_fitment"]


# ── Detector ──────────────────────────────────────────────────────────────────
def detect_objection(text: str) -> Optional[str]:
    """
    Scan a customer message or CRM note for objection keywords.
    Returns the battlecard key that matches, or None.
    """
    text_lower = text.lower()
    for key, card in BATTLECARDS.items():
        if re.search(card["trigger_keywords"], text_lower):
            return key
    return None


def get_battlecard(key: str, channel: str = "sms", **context) -> str:
    """
    Retrieve the battlecard script for a given key and channel.

    Args:
        key:     battlecard key (e.g. 'mileage_concern')
        channel: 'sms' | 'email' | 'call' | 'phone'
        context: template variables like model='INNOVA', part_description='Clutch Disc'

    Returns:
        Formatted script string.
    """
    card = BATTLECARDS.get(key, BATTLECARDS["warranty_fitment"])
    field_map = {
        "sms":   "sms_snippet",
        "email": "email_paragraph",
        "call":  "call_script",
        "phone": "call_script",
    }
    template = card.get(field_map.get(channel, "sms_snippet"), "")

    # Sensible defaults so curly brace placeholders never leak to customers
    context.setdefault("model", "Vehicle")
    context.setdefault("part_description", "part")
    context.setdefault("customer_name", "there")

    try:
        formatted = template.format(**context)
    except KeyError as e:
        missing = str(e).strip("'")
        context[missing] = context.get("model", "Vehicle")
        try:
            formatted = template.format(**context)
        except Exception:
            formatted = template

    # Clean any remaining {placeholder} patterns
    formatted = re.sub(r'\{[a-zA-Z_]+\}', lambda m: context.get(m.group(0)[1:-1], "Vehicle"), formatted)
    return formatted


def list_battlecards() -> list[dict]:
    """Return a summary list of all battlecards (for admin/dashboard)."""
    seen = set()
    cards = []
    for k, v in BATTLECARDS.items():
        if v["label"] not in seen:
            seen.add(v["label"])
            cards.append({
                "key": k,
                "label": v["label"],
                "subtitle": v.get("subtitle", ""),
                "icon": v.get("icon", "🛡️"),
                "description": v["description"],
                "triggers": v["trigger_keywords"],
            })
    return cards
