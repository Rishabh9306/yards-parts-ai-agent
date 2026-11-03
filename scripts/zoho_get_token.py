"""
scripts/zoho_get_token.py
--------------------------
Generates a fresh Zoho OAuth refresh token using Self Client flow.
Run this whenever your refresh token expires.

HOW TO USE:
  1. Go to https://api-console.zoho.in/
  2. Click your Self Client app
  3. Click "Generate Code" tab
  4. Paste this scope:
     ZohoCRM.modules.deals.ALL,ZohoCRM.modules.contacts.ALL,ZohoCRM.modules.notes.CREATE,ZohoCRM.org.READ
  5. Set duration to 10 minutes, click Create
  6. Copy the generated code
  7. Run this script: python scripts/zoho_get_token.py
  8. Paste the code when prompted
  9. Copy the ZOHO_REFRESH_TOKEN printed and update your .env
"""

import sys, os, httpx
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID     = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")

code = input("Paste the generated code from Zoho API Console:\n> ").strip()

resp = httpx.post(
    "https://accounts.zoho.in/oauth/v2/token",
    params={
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "authorization_code",
    },
    timeout=15,
)
data = resp.json()

if "refresh_token" in data:
    print("\n" + "=" * 55)
    print("SUCCESS — add this line to your .env:")
    print("=" * 55)
    print(f"\nZOHO_REFRESH_TOKEN={data['refresh_token']}\n")
else:
    print(f"\nERROR: {data}")
