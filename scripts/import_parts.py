"""
import_parts.py
--------------
Reads your Toyota master Excel catalog, cleans it, categorizes each part,
flags engine/transmission items as high-priority cadence targets, and
exports two files:
  - data/parts_cleaned.csv   → full cleaned catalog
  - data/cadence_targets.csv → only the high-priority parts for follow-up
"""

import pandas as pd
import re
import os
import sys

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

DEFAULT_EXCEL = os.path.join(OUT_DIR, "master_parts_catalog.xlsx")
FALLBACK_EXCEL = r"C:\Users\Admin\Downloads\master excel.xlsx"
EXCEL_PATH = DEFAULT_EXCEL if os.path.exists(DEFAULT_EXCEL) else FALLBACK_EXCEL

# ── 1. Load ──────────────────────────────────────────────────────────────────
print("Loading Excel...")
df = pd.read_excel(EXCEL_PATH, sheet_name="Master Parts Catalog")
print(f"  Raw rows: {len(df)}")

# ── 2. Rename columns to snake_case ──────────────────────────────────────────
df.columns = ["model", "part_description", "part_number", "price_usd", "image_url"]

# ── 3. Basic cleaning ────────────────────────────────────────────────────────
# Strip whitespace
df["model"]            = df["model"].str.strip().str.upper()
df["part_description"] = df["part_description"].str.strip()
df["part_number"]      = df["part_number"].str.strip().str.upper()
df["image_url"]        = df["image_url"].str.strip()

# Round prices to 2 dp
df["price_usd"] = df["price_usd"].round(2)

# Drop rows with missing critical fields
before = len(df)
df.dropna(subset=["part_number", "part_description", "price_usd"], inplace=True)
print(f"  Dropped {before - len(df)} rows with missing critical fields.")

# ── 4. Handle duplicate part numbers ─────────────────────────────────────────
# Same part number can exist across models — that's valid.
# Flag duplicates for reference only; don't drop them.
df["multi_model_part"] = df.duplicated(subset=["part_number"], keep=False)

# ── 5. Auto-categorise parts ─────────────────────────────────────────────────
CATEGORY_RULES = [
    ("Engine & Fluids",      r"engine|motor oil|flush|coolant|synthetic"),
    ("Transmission",         r"transmission|clutch|gear|differential"),
    ("Fuel & Injection",     r"injector|fuel|cleaner"),
    ("Filters",              r"filter|cleaner air|air element|cabin"),
    ("Brakes",               r"brake|shoe|disc|pad"),
    ("Suspension",           r"shock|absorber|arm|bush|bearing|strut|stabilizer"),
    ("Electrical & Lighting",r"bulb|lamp|battery|transmitter"),
    ("Tyres",                r"bridgestone|tyre|tire|\d{3}/\d{2}"),
    ("Wipers",               r"wiper|blade"),
    ("Body & Accessories",   r"moulding|molding|garnish|cover|visor|flap|mat|boot|door|bumper|grille|skid|cladding"),
    ("Cables & Controls",    r"cable|accelerator|hood|defroster|airmix|spiral|fuel lid"),
    ("Misc Hardware",        r"bolt|clamp|clip|cap|plug|bush|bracket|washer|arm sa"),
]

def categorise(desc: str) -> str:
    desc_lower = desc.lower()
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, desc_lower):
            return category
    return "Other"

df["category"] = df["part_description"].apply(categorise)

# ── 6. Flag cadence targets (engine/transmission quotes = re-engagement focus) ─
CADENCE_CATEGORIES = {"Engine & Fluids", "Transmission", "Fuel & Injection"}
df["cadence_priority"] = df["category"].isin(CADENCE_CATEGORIES)

# ── 7. Price tier tagging ─────────────────────────────────────────────────────
def price_tier(price: float) -> str:
    if price < 10:   return "Low"
    if price < 50:   return "Mid"
    if price < 150:  return "High"
    return "Premium"

df["price_tier"] = df["price_usd"].apply(price_tier)

# ── 8. Battlecard auto-tag ────────────────────────────────────────────────────
# Which objection battlecard is most relevant per part?
def battlecard_tag(desc: str) -> str:
    d = desc.lower()
    if re.search(r"engine|motor oil|flush", d):     return "mileage_compression"
    if re.search(r"transmission|clutch|gear", d):   return "mileage_compression"
    if re.search(r"coolant|injector", d):           return "compression"
    if re.search(r"filter", d):                     return "mileage"
    if re.search(r"brake|pad|disc|shoe", d):        return "freight_warranty"
    return "warranty"

df["battlecard"] = df["part_description"].apply(battlecard_tag)

# ── 9. Save outputs ───────────────────────────────────────────────────────────
cleaned_path = os.path.join(OUT_DIR, "parts_cleaned.csv")
df.to_csv(cleaned_path, index=False)
print(f"\n[OK] Full catalog saved -> {cleaned_path}")
print(f"   Total parts: {len(df)}")

cadence_df = df[df["cadence_priority"]].copy()
cadence_path = os.path.join(OUT_DIR, "cadence_targets.csv")
cadence_df.to_csv(cadence_path, index=False)
print(f"\n[CADENCE] Cadence targets saved -> {cadence_path}")
print(f"   Cadence-eligible parts: {len(cadence_df)}")

# ── 10. Print summary ─────────────────────────────────────────────────────────
print("\n=== Category Breakdown ===")
print(df.groupby("category")["part_number"].count().sort_values(ascending=False).to_string())

print("\n=== Models ===")
print(df["model"].value_counts().to_string())

print("\n=== Price Tiers ===")
print(df["price_tier"].value_counts().to_string())

print("\n=== Cadence Target Parts Sample ===")
print(cadence_df[["model","part_description","price_usd","battlecard"]].head(15).to_string())
