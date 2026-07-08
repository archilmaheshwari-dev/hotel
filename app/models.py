import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Date, Enum, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"          # draft, awaiting payment
    AWAITING_PAYMENT = "AWAITING_PAYMENT"  # payment link sent
    CONFIRMED = "CONFIRMED"      # payment verified
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"          # payment link expired unpaid


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, default=gen_uuid)
    room_number = Column(String, unique=True, nullable=False)
    room_type = Column(String, nullable=False)   # e.g. "Deluxe", "Suite"
    price_per_night = Column(Float, nullable=False)
    max_guests = Column(Integer, default=2)
    is_active = Column(Boolean, default=True)

    bookings = relationship("Booking", back_populates="room")


class Guest(Base):
    __tablename__ = "guests"

    id = Column(String, primary_key=True, default=gen_uuid)
    wa_id = Column(String, unique=True, nullable=False, index=True)  # WhatsApp phone id
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="guest")
    conversation = relationship("Conversation", back_populates="guest", uselist=False)


class Conversation(Base):
    """Tracks per-guest conversation state: recent message history + any partially
    collected booking info, as plain JSON (no agent framework needed)."""
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=gen_uuid)
    guest_id = Column(String, ForeignKey("guests.id"), unique=True, nullable=False)
    history_json = Column(Text, default="[]")          # list of {"role": "...", "content": "..."}
    pending_booking_json = Column(Text, default="{}")  # partially collected booking fields
    last_message_at = Column(DateTime, default=datetime.utcnow)

    guest = relationship("Guest", back_populates="conversation")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=gen_uuid)
    guest_id = Column(String, ForeignKey("guests.id"), nullable=False)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=False)

    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    guests_count = Column(Integer, default=1)

    total_amount = Column(Float, nullable=False)
    currency = Column(String, default="usd")

    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)

    stripe_checkout_session_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    guest = relationship("Guest", back_populates="bookings")
    room = relationship("Room", back_populates="bookings")


class ProcessedEvent(Base):
    """Idempotency guard for WhatsApp + Stripe webhook retries."""
    __tablename__ = "processed_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    source = Column(String, nullable=False)   # "whatsapp" | "stripe"
    event_id = Column(String, nullable=False, index=True)
    processed_at = Column(DateTime, default=datetime.utcnow)
