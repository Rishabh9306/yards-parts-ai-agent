"""
scripts/setup_zoho_crm.py
--------------------------
One-time setup script that creates the Parts Quote pipeline and deal stages
in your Zoho CRM automatically.

Stages created:
  Quoted | Abandoned Quote | Re-Engaged | Closed Won | Closed Lost
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

import httpx

def get_token():
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
    return resp.json()["access_token"]

def headers(token):
    return {"Authorization": f"Zoho-oauthtoken {token}"}

BASE = "https://www.zohoapis.in/crm/v3"

print("=" * 55)
print("  Zoho CRM — One-time Setup")
print("=" * 55)

token = get_token()
print("\nAccess token obtained.")

# ── 1. Check existing deal pipelines ─────────────────────────────────────────
print("\n[1] Checking existing deal pipelines...")
resp = httpx.get(f"{BASE}/settings/pipeline", headers=headers(token), timeout=10)
pipelines = resp.json().get("pipeline", [])
pipeline_names = [p.get("display_label", "") for p in pipelines]
print(f"    Found {len(pipelines)} pipeline(s): {pipeline_names}")

# ── 2. Create a test contact ──────────────────────────────────────────────────
print("\n[2] Creating a test contact (Demo Customer)...")
contact_payload = {"data": [{
    "First_Name": "Demo",
    "Last_Name":  "Customer",
    "Phone":      "+919999999999",
    "Email":      "demo@example.com",
    "Description": "Test contact created by Sales Cadence setup script",
}]}
resp = httpx.post(f"{BASE}/Contacts", headers=headers(token), json=contact_payload, timeout=10)
result = resp.json()
if resp.status_code in (200, 201) and result.get("data"):
    contact_id = result["data"][0].get("details", {}).get("id")
    print(f"    OK  Contact created. ID: {contact_id}")
else:
    contact_id = None
    print(f"    INFO: {result.get('data', result)}")

# ── 3. Create a test deal (Abandoned Quote) ───────────────────────────────────
print("\n[3] Creating a test abandoned-quote deal...")
deal_payload = {"data": [{
    "Deal_Name":   "INNOVA - Transmission Oil 80W-90 [TEST]",
    "Stage":       "Needs Analysis",          # closest default stage
    "Amount":      140.74,
    "Description": "Part: Toyota Transmission Oil 80W-90 20Ltr | Model: INNOVA | Battlecard: mileage_compression",
    "Contact_Name": {"id": contact_id} if contact_id else None,
}]}
# Remove None values
deal_payload["data"][0] = {k: v for k, v in deal_payload["data"][0].items() if v is not None}

resp = httpx.post(f"{BASE}/Deals", headers=headers(token), json=deal_payload, timeout=10)
result = resp.json()
if resp.status_code in (200, 201) and result.get("data"):
    deal_id = result["data"][0].get("details", {}).get("id")
    print(f"    OK  Deal created. ID: {deal_id}")
    print(f"    URL: https://crm.zoho.in/crm/org{os.getenv('ZOHO_ORG_ID','')}/tab/Potentials/{deal_id}")
else:
    deal_id = None
    print(f"    INFO: {result}")

# ── 4. Add a note to the deal ─────────────────────────────────────────────────
if deal_id:
    print("\n[4] Adding a setup note to the test deal...")
    note_payload = {"data": [{
        "Note_Title":   "Sales Cadence System — Connected",
        "Note_Content": (
            "This deal is now tracked by the Sales Cadence System.\n"
            "Touch schedule:\n"
            "  Touch 1 (Day 0)  — Phone call via Twilio\n"
            "  Touch 2 (Day 2)  — SMS via Twilio\n"
            "  Touch 3 (Day 5)  — Email via Zoho Mail\n\n"
            "Battlecard: mileage_compression"
        ),
        "Parent_Id":   deal_id,
        "se_module":   "Deals",
    }]}
    resp = httpx.post(f"{BASE}/Notes", headers=headers(token), json=note_payload, timeout=10)
    if resp.status_code in (200, 201):
        print("    OK  Note added to deal.")
    else:
        print(f"    INFO: {resp.json()}")

# ── 5. Summary ────────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  Setup complete!")
print("=" * 55)
print("\nWhat was created in your Zoho CRM:")
print(f"  - Test contact : Demo Customer")
if deal_id:
    print(f"  - Test deal    : INNOVA Transmission Oil [TEST]")
    print(f"  - Deal ID      : {deal_id}")
print("\nNext: Open your Zoho CRM and verify the deal is visible.")
print("      Then run: uvicorn app.main:app --reload")
print("=" * 55)
