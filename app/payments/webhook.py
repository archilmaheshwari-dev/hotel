import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, BookingStatus, Guest, Room, ProcessedEvent
from app.payments.stripe_client import construct_webhook_event
from app.whatsapp.client import send_text_message
from app.email.sender import send_booking_confirmed_email, send_payment_failed_email

router = APIRouter(prefix="/webhook/stripe", tags=["stripe"])


@router.post("")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = construct_webhook_event(raw_body, sig_header)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    # idempotency: Stripe retries undelivered/failed webhook events
    already_processed = (
        db.query(ProcessedEvent)
        .filter(ProcessedEvent.source == "stripe", ProcessedEvent.event_id == event["id"])
        .first()
    )
    if already_processed:
        return {"status": "duplicate"}
    db.add(ProcessedEvent(source="stripe", event_id=event["id"]))
    db.commit()

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_payment_success(data_object, db)
    elif event_type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        await _handle_payment_failure(data_object, db)

    return {"status": "ok"}


async def _handle_payment_success(session_obj: dict, db: Session):
    booking_id = session_obj.get("metadata", {}).get("booking_id")
    if not booking_id:
        return

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking or booking.status == BookingStatus.CONFIRMED:
        return  # already handled or not found

    booking.status = BookingStatus.CONFIRMED
    booking.stripe_payment_intent_id = session_obj.get("payment_intent")
    db.commit()

    guest = db.query(Guest).filter(Guest.id == booking.guest_id).first()
    room = db.query(Room).filter(Room.id == booking.room_id).first()

    # notify guest on WhatsApp
    await send_text_message(
        guest.wa_id,
        f"Payment received! Your {room.room_type} room is confirmed for "
        f"{booking.check_in} to {booking.check_out}. We look forward to hosting you, "
        f"{guest.name}!",
    )

    # notify owner by email
    send_booking_confirmed_email(
        guest_name=guest.name or "Unknown",
        guest_phone=guest.wa_id,
        room_type=room.room_type,
        check_in=str(booking.check_in),
        check_out=str(booking.check_out),
        amount=booking.total_amount,
        currency=booking.currency,
    )


async def _handle_payment_failure(session_obj: dict, db: Session):
    booking_id = session_obj.get("metadata", {}).get("booking_id")
    if not booking_id:
        return

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking or booking.status == BookingStatus.CONFIRMED:
        return

    booking.status = BookingStatus.EXPIRED
    db.commit()

    guest = db.query(Guest).filter(Guest.id == booking.guest_id).first()
    if guest:
        await send_text_message(
            guest.wa_id,
            "Your payment link expired and the room hold was released. "
            "Send me the dates again whenever you'd like to rebook!",
        )
        send_payment_failed_email(guest.wa_id, booking.id)
