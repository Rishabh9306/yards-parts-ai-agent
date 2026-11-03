"""
crm/zoho_client.py
------------------
Zoho CRM API wrapper.
Handles OAuth token refresh and deal/contact operations.
"""

import os
import httpx
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

ZOHO_CLIENT_ID     = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

ZOHO_API_BASE  = "https://www.zohoapis.in/crm/v3"   # use .com for US accounts
ZOHO_TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"

# Simple in-memory token cache (replace with Redis/DB for multi-instance)
_token_cache = {"access_token": None, "expires_at": datetime.utcnow()}


def _get_access_token() -> str:
    """
    Returns a valid Zoho access token, refreshing if expired.
    """
    if _token_cache["access_token"] and datetime.utcnow() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    resp = httpx.post(ZOHO_TOKEN_URL, params={
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id":     ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type":    "refresh_token",
    }, timeout=2.5)
    resp.raise_for_status()
    data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"]   = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 60)

    return _token_cache["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Zoho-oauthtoken {_get_access_token()}"}


# ── Deal operations ───────────────────────────────────────────────────────────

def get_deal(deal_id: str) -> dict:
    """Fetch a CRM deal by ID."""
    resp = httpx.get(f"{ZOHO_API_BASE}/Deals/{deal_id}", headers=_headers())
    resp.raise_for_status()
    return resp.json()["data"][0]


def update_deal_stage(deal_id: str, stage: str, notes: str = "") -> dict:
    """
    Update a deal's Stage field in Zoho CRM.

    Suggested stages:
      'Abandoned Quote' | 'Re-Engaged' | 'Closed Won' | 'Closed Lost'
    """
    payload = {"data": [{"Stage": stage}]}
    if notes:
        payload["data"][0]["Description"] = notes

    resp = httpx.put(
        f"{ZOHO_API_BASE}/Deals/{deal_id}",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def add_activity_note(deal_id: str, note: str, title: str = "Cadence Touch") -> dict:
    """
    Log a note/activity against a deal in Zoho CRM.
    Visible in the deal timeline.
    """
    payload = {
        "data": [{
            "Note_Title":   title,
            "Note_Content": note,
            "Parent_Id":    deal_id,
            "se_module":    "Deals",
        }]
    }
    resp = httpx.post(f"{ZOHO_API_BASE}/Notes", headers=_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()


def get_abandoned_deals() -> list[dict]:
    """
    Fetch all deals in 'Abandoned Quote' stage from Zoho CRM.
    Used for manual polling (webhook approach is preferred).
    """
    resp = httpx.get(
        f"{ZOHO_API_BASE}/Deals",
        headers=_headers(),
        params={"criteria": "(Stage:equals:Abandoned Quote)"},
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
