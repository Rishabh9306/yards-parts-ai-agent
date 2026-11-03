"""
scripts/verify_connections.py
------------------------------
Tests that Twilio + Zoho CRM credentials are valid.
Run before starting the server.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

print("=" * 55)
print("  Sales Cadence — Connection Verifier")
print("=" * 55)

# ── 1. Twilio ─────────────────────────────────────────────────────────────────
print("\n[1/2] Checking Twilio...")
try:
    from twilio.rest import Client
    sid   = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    phone = os.getenv("TWILIO_PHONE_NUMBER")

    client  = Client(sid, token)
    account = client.api.accounts(sid).fetch()

    print(f"  OK  Account Name  : {account.friendly_name}")
    print(f"  OK  Status        : {account.status}")
    print(f"  OK  From Number   : {phone}")
except Exception as e:
    print(f"  FAIL Twilio: {e}")

# ── 2. Zoho CRM ───────────────────────────────────────────────────────────────
print("\n[2/2] Checking Zoho CRM...")
try:
    import httpx

    resp = httpx.post(
        "https://accounts.zoho.in/oauth/v2/token",
        params={
            "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
            "client_id":     os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "grant_type":    "refresh_token",
        },
        timeout=10,
    )
    data = resp.json()

    if "access_token" in data:
        token = data["access_token"]
        print(f"  OK  Access token obtained (first 20 chars): {token[:20]}...")

        # Fetch org info
        org_resp = httpx.get(
            "https://www.zohoapis.in/crm/v3/org",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            timeout=10,
        )
        org = org_resp.json().get("org", [{}])[0]
        print(f"  OK  CRM Org Name   : {org.get('company_name', 'N/A')}")
        print(f"  OK  CRM Org ID     : {org.get('id', 'N/A')}")
    else:
        print(f"  FAIL Zoho token error: {data}")
except Exception as e:
    print(f"  FAIL Zoho: {e}")

print("\n" + "=" * 55)
print("  Done. Fix any FAIL items before starting the server.")
print("=" * 55)
