"""
scripts/seed_parts_to_db.py
----------------------------
Imports the cleaned parts CSV into the SQLite database.
Run this ONCE after import_parts.py has generated parts_cleaned.csv.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from app.models.db import init_db, SessionLocal, Part

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parts_cleaned.csv")


def seed():
    init_db()
    db = SessionLocal()

    df = pd.read_csv(CSV_PATH)
    print(f"Seeding {len(df)} parts into the database...")

    existing_count = db.query(Part).count()
    if existing_count > 0:
        print(f"  {existing_count} parts already in DB. Skipping (delete cadence.db to re-seed).")
        db.close()
        return

    parts = []
    for _, row in df.iterrows():
        part = Part(
            part_number      = str(row["part_number"]),
            part_description = str(row["part_description"]),
            model            = str(row["model"]),
            price_usd        = float(row["price_usd"]),
            category         = str(row.get("category", "")),
            price_tier       = str(row.get("price_tier", "")),
            battlecard       = str(row.get("battlecard", "warranty")),
            image_url        = str(row.get("image_url", "")),
            multi_model_part = bool(row.get("multi_model_part", False)),
            cadence_priority = bool(row.get("cadence_priority", False)),
        )
        parts.append(part)

    db.bulk_save_objects(parts)
    db.commit()
    db.close()

    print(f"  Done. {len(parts)} parts seeded.")
    cadence_count = df["cadence_priority"].sum()
    print(f"  {cadence_count} parts flagged as cadence targets (engine/transmission/fluids).")


if __name__ == "__main__":
    seed()
