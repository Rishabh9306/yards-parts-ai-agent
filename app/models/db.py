"""
models/db.py
------------
SQLAlchemy ORM models and database setup.
Tracks leads entering the cadence and every touch attempt made.
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "cadence.db").replace("\\", "/")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or DATABASE_URL == "sqlite:///./cadence.db":
    DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Lead ─────────────────────────────────────────────────────────────────────
class Lead(Base):
    """
    A customer who received a quote but hasn't purchased.
    One Lead = one abandoned quote episode.
    """
    __tablename__ = "leads"

    id                = Column(Integer, primary_key=True, index=True)
    zoho_deal_id      = Column(String(64), unique=True, index=True, nullable=True)
    customer_name     = Column(String(128), nullable=False)
    phone             = Column(String(20),  nullable=True)   # E.164 format: +91xxxxxxxxxx
    email             = Column(String(128), nullable=True)
    part_number       = Column(String(32),  nullable=True)
    part_description  = Column(String(256), nullable=True)
    model             = Column(String(32),  nullable=True)   # e.g. INNOVA, FORTUNER
    quote_value_usd   = Column(Float,       nullable=True)
    battlecard        = Column(String(64),  nullable=True)   # e.g. mileage_compression
    category          = Column(String(64),  nullable=True)   # e.g. Engine & Fluids
    items_json        = Column(Text,        default="[]")    # JSON array of quoted catalog items
    preferred_language= Column(String(8),   default="en")    # en | es
    status            = Column(String(32),  default="active")
    # active | re_engaged | closed_won | closed_lost | unsubscribed

    quote_date        = Column(DateTime, default=datetime.utcnow)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    touches           = relationship("Touch", back_populates="lead", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Lead id={self.id} name={self.customer_name} status={self.status}>"


# ── Touch ────────────────────────────────────────────────────────────────────
class Touch(Base):
    """
    A single contact attempt — Phone, SMS, or Email.
    """
    __tablename__ = "touches"

    id              = Column(Integer, primary_key=True, index=True)
    lead_id         = Column(Integer, ForeignKey("leads.id"), nullable=False)
    touch_number    = Column(Integer, nullable=False)    # 1, 2, or 3
    channel         = Column(String(16), nullable=False) # phone | sms | email
    scheduled_at    = Column(DateTime,  nullable=True)
    sent_at         = Column(DateTime,  nullable=True)
    outcome         = Column(String(32), nullable=True)
    # pending | sent | answered | voicemail | no_answer | replied | opened | bounced | failed
    battlecard_used = Column(String(64), nullable=True)
    message_sid     = Column(String(64), nullable=True)  # Twilio SID for tracking
    notes           = Column(Text,       nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow)

    lead            = relationship("Lead", back_populates="touches")

    def __repr__(self):
        return f"<Touch lead={self.lead_id} touch={self.touch_number} channel={self.channel} outcome={self.outcome}>"


# ── Part Catalog ─────────────────────────────────────────────────────────────
class Part(Base):
    """
    Automotive parts catalog — imported from inventory.
    """
    __tablename__ = "parts"

    id              = Column(Integer, primary_key=True, index=True)
    part_number     = Column(String(32), index=True, nullable=False)
    part_description= Column(String(256), nullable=False)
    model           = Column(String(32), nullable=False)
    price_usd       = Column(Float, nullable=False)
    category        = Column(String(64), nullable=True)
    price_tier      = Column(String(16), nullable=True)
    battlecard      = Column(String(64), nullable=True)
    image_url       = Column(String(512), nullable=True)
    multi_model_part= Column(Boolean, default=False)
    cadence_priority= Column(Boolean, default=False)

    def __repr__(self):
        return f"<Part {self.part_number} | {self.model} | {self.part_description[:40]}>"


# ── Call Session & Conversation Context ───────────────────────────────────────
class CallSession(Base):
    """
    Tracks state machine turns for live 2-way dynamic voice calls.
    Steps:
      greeting -> service_check -> project_scope -> technical_check -> assurance -> wrap_up -> confirm_end
    """
    __tablename__ = "call_sessions"

    id                  = Column(Integer, primary_key=True, index=True)
    lead_id             = Column(Integer, ForeignKey("leads.id"), nullable=False)
    call_sid            = Column(String(64), index=True, nullable=True)
    current_step        = Column(String(64), default="greeting")
    language            = Column(String(16), default="en-US")
    status              = Column(String(32), default="in_progress") # in_progress | completed | failed | transferred
    detected_objections = Column(Text, default="[]")                # JSON list of objections
    negotiated_price    = Column(Float, nullable=True)
    discount_pct        = Column(Float, default=0.0)
    silence_count       = Column(Integer, default=0)
    transcript          = Column(Text, default="[]")                # JSON list of speaker/turn dicts
    sms_summary_sent    = Column(Boolean, default=False)            # Post-call conclusion SMS dispatched
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead                = relationship("Lead")


class ConversationMessage(Base):
    """
    Unified cross-channel conversation store.
    Stores all turns across Voice, SMS, and Email so customer never repeats themselves.
    """
    __tablename__ = "conversation_messages"

    id          = Column(Integer, primary_key=True, index=True)
    lead_id     = Column(Integer, ForeignKey("leads.id"), nullable=False)
    channel     = Column(String(16), nullable=False) # voice | sms | email
    role        = Column(String(16), nullable=False) # assistant | customer | system
    content     = Column(Text,       nullable=False)
    intent      = Column(String(64), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    lead        = relationship("Lead")


# ── Automated Cart Mailing System (Completely Separate from Voice Cadence) ───
class CartAbandonment(Base):
    """
    Tracks online cart abandonments for the automatic scheduled mailing system:
      - Day 0 (End of Day): Initial cart recovery & purchase update
      - Day 3: Friendly reminder to place order
      - Day 4: Limited-time 4% discount incentive (YARDS4 coupon)
      - Day 6: Final call - coupon expiring in 24h
    """
    __tablename__ = "cart_abandonments"

    id                  = Column(Integer, primary_key=True, index=True)
    cart_token          = Column(String(64), unique=True, index=True) # e.g. CART-0418
    customer_name       = Column(String(128), nullable=False)
    customer_email      = Column(String(128), nullable=False)
    customer_phone      = Column(String(20),  nullable=True)
    model               = Column(String(32),  nullable=False) # e.g. FORTUNER, INNOVA
    part_description    = Column(String(256), nullable=False) # Primary summary
    part_number         = Column(String(32),  nullable=True)
    items_json          = Column(Text,        default="[]")   # JSON array of cart items
    total_value_usd     = Column(Float,       default=0.0)
    discounted_value_usd= Column(Float,       default=0.0)    # 4% off
    coupon_code         = Column(String(32),  default="YARDS4")
    current_day_step    = Column(Integer,     default=0)      # 0, 3, 4, 6
    status              = Column(String(32),  default="cart_abandoned") 
    # cart_abandoned | day0_sent | day3_sent | day4_sent | day6_sent | purchased | expired
    checkout_url        = Column(String(256), default="https://yardsparts.com/")
    cart_created_at     = Column(DateTime,    default=datetime.utcnow)
    last_email_sent_at  = Column(DateTime,    nullable=True)
    next_scheduled_date = Column(DateTime,    nullable=True)
    created_at          = Column(DateTime,    default=datetime.utcnow)
    updated_at          = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    email_logs          = relationship("CartEmailLog", back_populates="cart", cascade="all, delete-orphan")


class CartEmailLog(Base):
    """
    Records every email sent by the automated cart mailing engine.
    """
    __tablename__ = "cart_email_logs"

    id              = Column(Integer, primary_key=True, index=True)
    cart_id         = Column(Integer, ForeignKey("cart_abandonments.id"), nullable=False)
    day_step        = Column(Integer, nullable=False) # 0, 3, 4, 6
    email_to        = Column(String(128), nullable=False)
    subject         = Column(String(256), nullable=False)
    message_id      = Column(String(64),  nullable=True)
    status          = Column(String(32),  default="sent") # sent | failed | simulated
    pdf_attached    = Column(Boolean,     default=True)
    sent_at         = Column(DateTime,    default=datetime.utcnow)

    cart            = relationship("CartAbandonment", back_populates="email_logs")


# ── VIN Vehicle Records ────────────────────────────────────────────────────────
class VehicleRecord(Base):
    __tablename__ = "vehicle_records"

    id                  = Column(Integer, primary_key=True, index=True)
    vin                 = Column(String(32), unique=True, index=True, nullable=False)
    year                = Column(Integer, nullable=False)
    make                = Column(String(64), nullable=False)
    model               = Column(String(64), nullable=False)
    trim                = Column(String(64), nullable=True)
    body_class          = Column(String(64), nullable=True)
    engine_displacement = Column(Float, nullable=True)
    engine_cylinders    = Column(Integer, nullable=True)
    fuel_type           = Column(String(32), nullable=True)
    transmission        = Column(String(128), nullable=True)
    drive_type          = Column(String(32), nullable=True)
    plant_country       = Column(String(64), nullable=True)
    status              = Column(String(32), default="DECODED")
    raw_json            = Column(Text, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)

    quotes              = relationship("QuoteProposal", back_populates="vehicle")


# ── Formal B2B Quotations ─────────────────────────────────────────────────────
class QuoteProposal(Base):
    __tablename__ = "quote_proposals"

    id                  = Column(Integer, primary_key=True, index=True)
    quote_number        = Column(String(32), unique=True, index=True, nullable=False) # e.g. YP-2026-0001
    customer_name       = Column(String(128), nullable=False)
    customer_phone      = Column(String(32), nullable=True)
    customer_email      = Column(String(128), nullable=True)
    destination_zip     = Column(String(10), default="43215")
    
    vehicle_id          = Column(Integer, ForeignKey("vehicle_records.id"), nullable=True)
    vehicle_summary     = Column(String(256), nullable=True)
    
    parts_subtotal      = Column(Float, default=0.0)
    total_core_charges  = Column(Float, default=0.0)
    total_discounts     = Column(Float, default=0.0)
    handling_fee        = Column(Float, default=15.0)
    freight_charge      = Column(Float, default=0.0)
    freight_zone        = Column(Integer, default=5)
    tax_amount          = Column(Float, default=0.0)
    grand_total         = Column(Float, default=0.0)
    
    status              = Column(String(32), default="DRAFT") # DRAFT | SENT | APPROVED | EXPIRED
    pdf_path            = Column(String(256), nullable=True)
    valid_until         = Column(DateTime, nullable=True)
    
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vehicle             = relationship("VehicleRecord", back_populates="quotes")
    items               = relationship("QuoteLineItem", back_populates="quote", cascade="all, delete-orphan")


class QuoteLineItem(Base):
    __tablename__ = "quote_line_items"

    id                  = Column(Integer, primary_key=True, index=True)
    quote_id            = Column(Integer, ForeignKey("quote_proposals.id"), nullable=False)
    part_name           = Column(String(256), nullable=False)
    part_number         = Column(String(64), nullable=True)
    hollander_number    = Column(String(32), nullable=True)
    oem_part_number     = Column(String(64), nullable=True)
    category            = Column(String(64), nullable=True)
    
    unit_cost           = Column(Float, default=0.0)
    selling_price       = Column(Float, default=0.0)
    core_charge         = Column(Float, default=0.0)
    discount_amount     = Column(Float, default=0.0)
    quantity            = Column(Integer, default=1)
    line_subtotal       = Column(Float, default=0.0)
    
    fitment_status      = Column(String(32), default="VERIFIED_COMPATIBLE")
    fitment_notes       = Column(Text, nullable=True)
    evidence_json       = Column(Text, default="[]")
    
    created_at          = Column(DateTime, default=datetime.utcnow)

    quote               = relationship("QuoteProposal", back_populates="items")


# ── Create all tables ─────────────────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(bind=engine)


# ── Dependency for FastAPI routes ─────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
