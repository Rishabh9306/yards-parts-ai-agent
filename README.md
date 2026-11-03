# Yards & Parts Automotive — Platform & Cadence Engine 🚗🔧

**B2B Salvage Yard Interchange, VIN Decoding, Dynamic Quoting & Autonomous Omnichannel Sales Recovery**

---

## 📌 Executive Overview

**Yards & Parts Automotive** is an end-to-end B2B automotive parts quoting and abandoned-quote sales cadence platform built for salvage yards, dismantlers, and automotive recycling distributors. 

It unifies:
1. **Live VIN Decoding & Vehicle Specification:** Integrated directly with the NHTSA vPIC API to decode year, make, model, trim, displacement, cylinder count, aspiration, and transmission.
2. **Hollander Interchange & Powertrain Matching:** Instant cross-referencing between decoded vehicle chassis specifications and salvage yard inventory with algorithmic fitment verification scoring (95% Verified Compatible, 55% Requires Review).
3. **4-Tier Margin & Pricing Safeguards:** Real-time enforcement of $\ge 20\%$ gross margin protection, part mileage/grade markups, refundable core deposits, and commercial warranty tiers.
4. **LTL Freight Logistics:** Instant weight-bracketed freight estimation across regional, continental, and remote destination ZIP codes with liftgate support.
5. **Formal B2B PDF Quotation Engine:** Automated generation of professional, itemized PDF quotes (`Quote_YP-XXXX-XXXX.pdf`) using ReportLab with company branding, fitment badges, core deposit return policies, and live online checkout links.
6. **Omnichannel AI Sales Cadence:** Multi-touch recovery across **Voice (Twilio Phone Call)**, **SMS (Twilio)**, and **Email (Gmail SMTP)** powered by 13 context-aware objection battlecards, live negotiation handling, and automated cart abandonment sequences (Day 0, Day 3, Day 4 with `YARDS4` 4% discount, and Day 6 final call).
7. **Zoho CRM Bidirectional Synchronization:** Automatic ingestion of abandoned quotes via webhooks and real-time logging of call outcomes, email dispatches, and order confirmations back to CRM leads.

---

## 🏛️ System Architecture

```
                                  ┌───────────────────────────────┐
                                  │      Customer / Shop Lead     │
                                  └──────────────┬────────────────┘
                                                 │
                                                 ▼
             ┌───────────────────────────────────────────────────────────────────────┐
             │                          WEB INTERFACES                               │
             ├───────────────────────────┬───────────────────────────────────────────┤
             │   VIN Quoting Engine      │        Sales Rep Dashboard                │
             │      (/quoting)           │          (/dashboard/rep)                 │
             └─────────────┬─────────────┴─────────────────────┬─────────────────────┘
                           │                                   │
                           ▼                                   ▼
 ┌──────────────────────────────────┐        ┌───────────────────────────────────────┐
 │       NHTSA vPIC Decoder         │        │    Omnichannel Dispatch Engine        │
 │  (VIN -> Engine / Transmission)  │        │  (Voice Calls, SMS, Contextual Email) │
 └─────────────────┬────────────────┘        └─────────────────┬─────────────────────┘
                   │                                           │
                   ▼                                           ▼
 ┌──────────────────────────────────┐        ┌───────────────────────────────────────┐
 │   Hollander Interchange Engine   │        │     Twilio Voice & Conversational AI  │
 │  (Fitment & Cross-Reference)     │        │    (Real-time Barge-In & Negotiation) │
 └─────────────────┬────────────────┘        └─────────────────┬─────────────────────┘
                   │                                           │
                   ▼                                           ▼
 ┌──────────────────────────────────┐        ┌───────────────────────────────────────┐
 │  Pricing Safeguards & Freight    │        │      Twilio SMS & Gmail SMTP          │
 │  (>=20% Margin, Core, LTL Rates) │        │   (Live PDF Links & YARDS4 Coupon)    │
 └─────────────────┬────────────────┘        └─────────────────┬─────────────────────┘
                   │                                           │
                   ▼                                           ▼
 ┌──────────────────────────────────┐        ┌───────────────────────────────────────┐
 │    Formal PDF Quote Service      │        │      Zoho CRM & SQLite Database       │
 │   (ReportLab Vector Generation)  │        │   (Bi-directional Sync & Audit Trail) │
 └──────────────────────────────────┘        └───────────────────────────────────────┘
```

---

## 📁 Repository Directory Structure

```
sales-cadence/
│
├── README.md                           # Master system specification & packaging manifest
├── requirements.txt                    # Python dependencies (FastAPI, ReportLab, Twilio, SQLAlchemy...)
├── .env                                # Local environment secrets (Twilio, Zoho, Gmail SMTP, URLs)
├── .env.example                        # Clean template for environment configuration
├── cadence.db                          # Primary SQLite production database
├── run.py                              # Universal cross-platform launcher (Uvicorn server)
├── run_services.py                     # Unified supervisor (Cloudflare quick tunnel + Uvicorn server)
├── start_windows.bat                   # 1-Click Windows execution script
├── start_mac.sh                        # 1-Click macOS / Linux execution script
├── cloudflared.exe                     # Bundled Cloudflare Tunnel binary for public webhook tunneling
│
├── app/                                # Core Application Package
│   ├── __init__.py
│   ├── main.py                         # FastAPI web server, REST endpoints, and UI template routing
│   ├── cadence_engine.py               # Touch orchestration engine & APScheduler cron jobs
│   ├── battlecards.py                  # 13 objection-handling scripts (Warranty, Fitment, Price, OEM vs Aftermarket)
│   ├── voice_dialogue.py               # Conversational AI dialogue tree for Twilio Voice calls
│   │
│   ├── comms/                         # Communication Channels
│   │   ├── __init__.py
│   │   ├── twilio_voice.py             # Twilio Voice webhook handler, TwiML generation, and live streaming
│   │   ├── twilio_sms.py               # Twilio Programmable SMS client & localized message builder
│   │   ├── email_client.py             # Gmail SMTP HTML email composer with PDF attachment support
│   │   ├── cart_auto_mailer.py         # 4-stage autonomous cart recovery mailer (Days 0, 3, 4, 6)
│   │   └── pdf_generator.py            # Legacy transactional PDF quote generator
│   │
│   ├── crm/                           # CRM Integrations
│   │   ├── __init__.py
│   │   ├── zoho_client.py              # Zoho CRM REST API v2 client (Leads, Deals, Notes)
│   │   └── webhook_dispatcher.py       # Asynchronous webhook dispatcher for CRM events
│   │
│   ├── models/                        # Persistence Layer
│   │   ├── __init__.py
│   │   └── db.py                       # SQLAlchemy ORM models (Lead, Part, Touch, CallSession, CartAbandonment)
│   │
│   ├── services/                      # Quoting & Interchanging Domain Logic
│   │   ├── vin_service.py              # Live NHTSA vPIC decoder with caching & validation
│   │   ├── hollander_service.py        # Hollander Interchange cross-referencing & fitment scoring
│   │   ├── pricing_service.py          # Cost markup, margin safeguard (>=20%), warranty & core deposits
│   │   ├── freight_service.py          # LTL weight bracket, destination ZIP zone & liftgate fee calculator
│   │   ├── pdf_quote_service.py        # Formal ReportLab PDF quote generator (Clean B2B vector layout)
│   │   ├── quote_manager.py            # Quote lifecycle state management, sequence generation & audit trail
│   │   └── web_chat_service.py         # Web-based quoting chat assistant & customer support dispatch
│   │
│   └── static/                        # Static UI Assets
│       └── toyota_logo.png             # Historical reference asset
│
├── data/                              # Inventory Data Pipeline & Excel Catalogues
│   ├── master_parts_catalog.xlsx       # Primary consolidated Excel workbook (Master Parts Catalog)
│   ├── parts_cleaned.csv               # 659 cleaned, categorized, price-tiered inventory records
│   ├── cadence_targets.csv             # 108 high-value drivetrain/mechanical parts prioritized for cadence
│   │
│   └── raw_excel_models/               # Original individual vehicle model Excel workbooks:
│       ├── crysta.xlsx                 # Innova Crysta parts workbook
│       ├── fortuner.xlsx               # Fortuner parts workbook
│       ├── glanza.xlsx                 # Glanza parts workbook
│       ├── hicross.xlsx                # Innova Hycross parts workbook
│       ├── hyryder.xlsx                # Urban Cruiser Hyryder parts workbook
│       ├── innova.xlsx                 # Classic Innova parts workbook
│       ├── qualis.xlsx                 # Qualis parts workbook
│       ├── urban cruiser.xlsx          # Urban Cruiser parts workbook
│       └── yaris.xlsx                  # Yaris parts workbook
│
├── scripts/                           # Database Seeding & Operational Automation
│   ├── import_parts.py                 # Ingests master_parts_catalog.xlsx, cleans and exports CSVs
│   ├── seed_parts_to_db.py             # Seeds parts_cleaned.csv into SQLite cadence.db
│   ├── setup_zoho_crm.py               # Configures Zoho CRM custom fields and test leads
│   ├── verify_connections.py           # Connectivity verification for Twilio, Zoho, and SMTP
│   └── zoho_get_token.py               # Generates Zoho OAuth 2.0 access and refresh tokens
│
├── templates/                         # Frontend HTML5 / TailwindCSS / AlpineJS Interfaces
│   ├── quoting_engine.html             # VIN to Hollander B2B Quoting Engine & PDF proposal generator
│   ├── dashboard_rep.html              # Sales Rep Cockpit with 1-click calls, SMS, emails & lead history
│   └── dashboard_auto_mailer.html      # Autonomous 4-stage Cart Abandonment follow-up monitor
│
└── temp_quotes/                       # Generated Formal PDF Quotations
    ├── Quote_YP-2026-0001_*.pdf        # Example generated quotation documents
    └── ...
```

---

## 📊 Dataset & Data Engineering Pipeline

All original catalog data used across this platform was ingested from raw multi-sheet Excel files. The repository preserves both the raw source files and the production-cleaned outputs:

1. **Source Excel Files (`data/raw_excel_models/`):**
   - Individual Excel spreadsheets for each vehicle line containing genuine part numbers, descriptions, prices, and image URLs: `crysta.xlsx`, `fortuner.xlsx`, `glanza.xlsx`, `hicross.xlsx`, `hyryder.xlsx`, `innova.xlsx`, `qualis.xlsx`, `urban cruiser.xlsx`, `yaris.xlsx`.
2. **Master Consolidated Workbook (`data/master_parts_catalog.xlsx`):**
   - 659 total parts across all models with standardized schema (`model`, `part_description`, `part_number`, `price_usd`, `image_url`).
3. **Data Transformation (`scripts/import_parts.py`):**
   - Categorizes each part into one of 13 system categories (`Engine & Fluids`, `Transmission`, `Brakes`, `Suspension`, `Electrical`, etc.).
   - Computes price tiers (`Low`, `Mid`, `High`, `Premium`).
   - Maps appropriate battlecards based on mechanical vulnerability and wear patterns.
   - Flags 108 high-priority drivetrain and mechanical parts (`data/cadence_targets.csv`) for proactive cadence follow-up.
4. **Database Seeding (`scripts/seed_parts_to_db.py`):**
   - Bulk-inserts the 659 catalog items into the SQLite database (`cadence.db`).

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12 installed
- Git installed

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/sales-cadence.git
cd sales-cadence

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

| Variable | Description | Example |
| :--- | :--- | :--- |
| TWILIO_ACCOUNT_SID | Twilio Account SID | ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx |
| TWILIO_AUTH_TOKEN | Twilio Auth Token | your_auth_token_here |
| TWILIO_PHONE_NUMBER| Twilio Outbound Number | +1xxxxxxxxxx |
| GMAIL_USER | Gmail address for SMTP | your_email@gmail.com |
| GMAIL_APP_PASSWORD | Google 16-char App Password | your_16_char_app_password |
| `SENDER_NAME` | Sender display name | `Yards & Parts Automotive` |
| ZOHO_CLIENT_ID | Zoho CRM API Client ID | your_client_id_here |
| ZOHO_CLIENT_SECRET | Zoho CRM API Secret | your_client_secret_here |
| ZOHO_REFRESH_TOKEN | Zoho CRM Refresh Token | your_refresh_token_here |
| `DATABASE_URL` | SQLAlchemy Database URL | `sqlite:///./cadence.db` |
| `TWIML_BASE_URL` | Public webhook tunnel URL | `https://your-tunnel.trycloudflare.com` |

### 4. Data Ingestion & Database Initialization
```bash
# Clean master Excel data and generate CSVs
python scripts/import_parts.py

# Seed database with the cleaned parts catalog
python scripts/seed_parts_to_db.py
```

### 5. Running the Application

#### Option A: Local Development Server
```bash
python run.py
```
Or via script:
- **Windows:** Double-click `start_windows.bat`
- **macOS / Linux:** Run `./start_mac.sh`

#### Option B: Live Webhook Mode (Cloudflare Tunnel + Uvicorn)
For live Twilio Voice, Twilio SMS webhooks, and phone interaction:
```bash
python run_services.py
```
*This starts a Cloudflare tunnel, prints your public URL, updates `TWIML_BASE_URL` in `.env`, and launches the FastAPI server with reload enabled.*

---

## 🌐 Application Web Interfaces

| Interface | URL | Description |
| :--- | :--- | :--- |
| **VIN Quoting Engine** | `http://localhost:8000/quoting` | 4-step workflow: VIN decode, Hollander match, pricing safeguard, and formal PDF generation. |
| **Sales Rep Cockpit** | `http://localhost:8000/dashboard/rep` | Real-time queue of abandoned quotes, lead details, 1-click calls, SMS, emails, and full conversation transcripts. |
| **Follow-up Automation** | `http://localhost:8000/dashboard/auto-mailer` | Visual pipeline tracking 4-stage cart abandonment emails (Day 0, Day 3, Day 4 with `YARDS4`, Day 6). |
| **API Documentation** | `http://localhost:8000/docs` | Interactive OpenAPI / Swagger documentation for all REST endpoints. |

---

## 🛡️ Business Safeguards & Logic

### 1. 20% Gross Margin Protection
The system calculates:
$$\text{Gross Margin} = \frac{\text{Net Parts Price} - \text{Unit Cost}}{\text{Net Parts Price}}$$
If the sales representative attempts to lower the markup below 20%, the system flags a visual warning:
$$\text{Safeguard Activated: Minimum 20.0\% Margin Required}$$

### 2. Hollander Fitment Scoring
- **Verified Compatible (95% Confidence):** Exact match across displacement, cylinder configuration, aspiration, and vehicle generation range.
- **Requires Review (55% Confidence):** Partial match (e.g., matching displacement or generation, but differing aspiration or transmission code requiring mechanic review).

### 3. Core Deposit Policy
Standard \$150.00 – \$250.00 refundable core deposit added to high-value mechanical assemblies. 100% refunded when rebuildable core unit is returned within 30 days via prepaid bill of lading (BOL).

### 4. Commercial Incentive
On Day 4 of cart abandonment or upon explicit sales rep negotiation on a voice call, a pre-authorized **4% trade discount** is unlocked via coupon code **`YARDS4`** alongside free express freight dispatch.

---

## 🧪 Testing & Verification

Run the built-in connection verification script to confirm all API credentials and services:
```bash
python scripts/verify_connections.py
```

Test generating a formal quote PDF directly:
```bash
python -c "
from app.services.pdf_quote_service import generate_formal_quote_pdf
test_data = {
    'quote_number': 'YP-TEST-0001',
    'created_at': 'November 03, 2026',
    'customer_name': 'Test Fleet Garage',
    'customer_phone': '+1 (555) 123-4567',
    'customer_email': 'fleet@example.com',
    'destination_zip': '77001',
    'vehicle_name': '2018 Honda Civic EX',
    'vin': '19XFC2F5XJE000001',
    'engine': '2.0L I4 Gasoline',
    'transmission': 'CVT Automatic',
    'items': [{'part_name': '2.0L I4 Engine Assembly', 'hollander_number': '300-08921', 'oem_number': '10002-5BA-A00', 'part_type': 'Engine', 'condition_grade': 'Grade A (48,200 mi)', 'unit_price': 812.50, 'core_deposit': 150.00}],
    'financials': {'parts_subtotal': 812.50, 'core_deposit_total': 150.00, 'freight_fee': 175.00, 'handling_fee': 25.00, 'account_discount_pct': 0.0, 'account_discount_amount': 0.0, 'tax_rate_pct': 0.0, 'tax_amount': 0.0, 'grand_total': 1162.50}
}
out = generate_formal_quote_pdf(test_data, 'temp_quotes/test_formal.pdf')
print('Generated test PDF at:', out)
"
```

---

## 📄 License & Intellectual Property
Copyright © 2026 Yards & Parts Automotive. All rights reserved. Built for B2B salvage yard interchange and autonomous automotive parts quote recovery.
