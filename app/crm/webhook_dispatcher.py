"""
crm/webhook_dispatcher.py
-------------------------
Standard Generic Outbound CRM Webhook Dispatcher for Yards & Parts.
Dispatches signed JSON event payloads to Kiran's in-house CRM or any configured webhook URL:
  - quote.created: When a new B2B quote and PDF are generated
  - call.completed: When a voice dialogue state machine turn concludes
  - call.started: When an outbound or inbound call initiates
  - sms.received: When an inbound SMS is received
  - cart.recovered: When an abandoned cart is claimed
"""

import os
import time
import hmac
import hashlib
import json
import uuid
import httpx
from datetime import datetime
from typing import Dict, Any, List

# Configurable webhook URL and secret from environment
CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "https://crm.yardsparts.demo/api/v1/events")
CRM_WEBHOOK_SECRET = os.getenv("CRM_WEBHOOK_SECRET", "yp_demo_webhook_secret")

# In-memory buffer of recent dispatched webhook events for UI audit feed
RECENT_WEBHOOK_EVENTS: List[Dict[str, Any]] = []


def dispatch_crm_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constructs a standardized JSON event envelope, generates an HMAC-SHA256 signature,
    and posts to the configured CRM webhook endpoint.
    """
    event_id = f"evt_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    timestamp = datetime.utcnow().isoformat() + "Z"

    payload = {
        "eventId": event_id,
        "timestamp": timestamp,
        "eventType": event_type,
        "source": "yards-parts-platform",
        "version": "1.0",
        "data": data,
    }

    payload_json = json.dumps(payload, default=str)

    # Compute HMAC-SHA256 signature
    sig = hmac.new(
        CRM_WEBHOOK_SECRET.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "YardsParts-CRM-Dispatcher/2.0",
        "X-YardsParts-Event": event_type,
        "X-YardsParts-Event-Id": event_id,
        "X-YardsParts-Timestamp": timestamp,
        "X-YardsParts-Signature": f"sha256={sig}",
    }

    delivery_status = "simulated"
    status_code = 200
    error_msg = None

    # Attempt real delivery if a live non-demo URL is configured
    is_demo = any(d in CRM_WEBHOOK_URL.lower() for d in [".demo", ".example", ".invalid", "localhost", "127.0.0.1"])
    if CRM_WEBHOOK_URL and not is_demo:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.post(CRM_WEBHOOK_URL, content=payload_json, headers=headers)
                status_code = resp.status_code
                delivery_status = "delivered" if resp.is_success else "failed"
        except Exception as e:
            delivery_status = "network_error"
            error_msg = str(e)
            status_code = 503

    event_record = {
        "eventId": event_id,
        "timestamp": timestamp,
        "eventType": event_type,
        "targetUrl": CRM_WEBHOOK_URL,
        "deliveryStatus": delivery_status,
        "statusCode": status_code,
        "errorMessage": error_msg,
        "payload": payload,
    }

    # Store in FIFO audit buffer (keep last 50 events)
    RECENT_WEBHOOK_EVENTS.insert(0, event_record)
    if len(RECENT_WEBHOOK_EVENTS) > 50:
        RECENT_WEBHOOK_EVENTS.pop()

    return event_record


def get_recent_webhook_events(limit: int = 25) -> List[Dict[str, Any]]:
    """Returns recently dispatched webhook events for UI display."""
    return RECENT_WEBHOOK_EVENTS[:limit]
