"""
Plain-Python replacement for the old LangGraph agent layer. One function,
`process_message`, does everything:

  1. classify the message as "booking" or "faq"
  2. if faq -> answer using retrieved RAG context
  3. if booking -> merge new info into any partially-collected booking fields,
     ask for whatever's missing, or create the booking + Stripe checkout link
     once everything is present

Conversation memory is just two JSON blobs on the Conversation row:
  - history_json: last N messages (for context on follow-ups)
  - pending_booking_json: whatever booking fields have been collected so far
"""
import json
from datetime import datetime, date

from groq import Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Room, Booking, BookingStatus, Guest, Conversation
from app.payments.stripe_client import create_checkout_session
from app.rag.retriever import retrieve_context

client = Groq(api_key=settings.GROQ_API_KEY)
MODEL = settings.GROQ_MODEL

MAX_HISTORY_MESSAGES = 10
BOOKING_FIELDS = ["room_type", "check_in", "check_out", "guests_count", "guest_name", "guest_email"]


def _load_history(conversation: Conversation) -> list[dict]:
    return json.loads(conversation.history_json or "[]")


def _save_history(conversation: Conversation, history: list[dict]) -> None:
    conversation.history_json = json.dumps(history[-MAX_HISTORY_MESSAGES:])


def _load_pending(conversation: Conversation) -> dict:
    return json.loads(conversation.pending_booking_json or "{}")


def _save_pending(conversation: Conversation, pending: dict) -> None:
    conversation.pending_booking_json = json.dumps(pending)


def classify_intent(message: str) -> str:
    """Returns 'booking' or 'faq'."""
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=10,
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the guest's WhatsApp message as exactly one word: "
                    "'booking' (wants to book/check availability/modify a reservation, "
                    "or is providing booking details like dates/names/emails) or "
                    "'faq' (general question about amenities, policies, pricing, location). "
                    "Reply with only that one word."
                ),
            },
            {"role": "user", "content": message},
        ],
    )
    answer = resp.choices[0].message.content.strip().lower()
    return "booking" if "book" in answer else "faq"


def answer_faq(message: str) -> str:
    context = retrieve_context(message)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        max_tokens=200,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful hotel front-desk assistant answering guest questions "
                    "over WhatsApp. Use ONLY the context below. Keep answers short (2-4 "
                    "sentences), friendly, no markdown. If the context doesn't contain the "
                    "answer, say you'll check with the team and follow up.\n\nContext:\n"
                    f"{context or 'No context available.'}"
                ),
            },
            {"role": "user", "content": message},
        ],
    )
    return resp.choices[0].message.content.strip()


def extract_booking_fields(history: list[dict], pending: dict, latest_message: str) -> dict:
    """Ask the LLM to merge the latest message into the pending booking dict and
    return the updated fields as JSON. Returns dict with BOOKING_FIELDS keys
    (None if still unknown) plus "ready_to_book": bool."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    system_prompt = (
        "You track hotel booking details across a WhatsApp conversation. You are given "
        "the fields collected so far (some may be null) and the guest's newest message. "
        "Update the fields based on the newest message, keeping any previously known "
        "fields that the new message doesn't change. Resolve relative dates ('next "
        f"Friday', 'tomorrow') into YYYY-MM-DD using today = {today}.\n\n"
        "Respond with ONLY a JSON object with exactly these keys: "
        "room_type (string or null), check_in (YYYY-MM-DD or null), "
        "check_out (YYYY-MM-DD or null), guests_count (integer or null), "
        "guest_name (string or null), guest_email (string or null), "
        "ready_to_book (true only if ALL six fields above are non-null and "
        "check_out is after check_in, else false).\n"
        "No prose, no markdown fences — JSON only."
    )

    user_content = json.dumps({"fields_so_far": pending, "newest_message": latest_message})

    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fall back to whatever we had before, nothing extracted
        merged = dict(pending)
        merged["ready_to_book"] = False
        return merged


def _missing_field_names(fields: dict) -> list[str]:
    return [f for f in BOOKING_FIELDS if not fields.get(f)]


def handle_booking(db: Session, guest: Guest, conversation: Conversation, message: str) -> tuple[str, str | None]:
    history = _load_history(conversation)
    pending = _load_pending(conversation)

    fields = extract_booking_fields(history, pending, message)
    _save_pending(conversation, {k: fields.get(k) for k in BOOKING_FIELDS})

    if not fields.get("ready_to_book"):
        missing = _missing_field_names(fields)
        missing_str = ", ".join(missing) if missing else "a couple more details"
        reply = (
            f"Happy to help you book! Could you share your {missing_str}? "
            f"For example: 'Deluxe room, June 20 to June 23, 2 guests, "
            f"John Doe, john@email.com'."
        )
        return reply, None

    # all fields present — validate against DB and create the booking
    room_type = fields["room_type"]
    check_in = date.fromisoformat(fields["check_in"])
    check_out = date.fromisoformat(fields["check_out"])
    guests_count = int(fields["guests_count"])
    guest_name = fields["guest_name"]
    guest_email = fields["guest_email"]

    if check_out <= check_in:
        _save_pending(conversation, {})  # reset, something's off — start over
        return "Check-out needs to be after check-in — could you share the dates again?", None

    room = (
        db.query(Room)
        .filter(Room.room_type.ilike(f"%{room_type}%"), Room.is_active == True)  # noqa: E712
        .first()
    )
    if not room:
        return (
            f"Sorry, I couldn't find a '{room_type}' room. "
            f"We currently offer: Standard, Deluxe, and Suite. Which would you like?",
            None,
        )

    overlap = (
        db.query(Booking)
        .filter(
            Booking.room_id == room.id,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.AWAITING_PAYMENT]),
            Booking.check_in < check_out,
            Booking.check_out > check_in,
        )
        .first()
    )
    if overlap:
        return (
            f"The {room.room_type} room is already booked for part of that period. "
            f"Could you try different dates or another room type?",
            None,
        )

    nights = (check_out - check_in).days
    total_amount = nights * room.price_per_night

    guest.name = guest_name
    guest.email = guest_email

    booking = Booking(
        guest_id=guest.id,
        room_id=room.id,
        check_in=check_in,
        check_out=check_out,
        guests_count=guests_count,
        total_amount=total_amount,
        currency="usd",
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    session = create_checkout_session(
        booking_id=booking.id,
        amount=total_amount,
        currency=booking.currency,
        description=f"{room.room_type} room — {nights} night(s)",
    )
    booking.stripe_checkout_session_id = session.id
    booking.status = BookingStatus.AWAITING_PAYMENT
    db.commit()

    _save_pending(conversation, {})  # booking done, clear pending state

    reply = (
        f"Great, here's your booking summary:\n"
        f"Room: {room.room_type}\n"
        f"Check-in: {check_in}\n"
        f"Check-out: {check_out}\n"
        f"Guests: {guests_count}\n"
        f"Total: {total_amount:.2f} USD ({nights} night(s))\n\n"
        f"Please complete payment to confirm: {session.url}\n"
        f"This link expires in 30 minutes."
    )
    return reply, session.url


def process_message(db: Session, guest: Guest, conversation: Conversation, message: str) -> tuple[str, str | None]:
    """Main entry point called from the WhatsApp webhook. Returns (reply_text, checkout_url)."""
    history = _load_history(conversation)
    pending = _load_pending(conversation)

    # if we're already mid-booking-collection, stay in booking mode regardless of classifier
    if pending:
        intent = "booking"
    else:
        intent = classify_intent(message)

    if intent == "faq":
        reply = answer_faq(message)
        checkout_url = None
    else:
        reply, checkout_url = handle_booking(db, guest, conversation, message)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    _save_history(conversation, history)

    db.commit()
    return reply, checkout_url
