import time

import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(
    booking_id: str,
    amount: float,
    currency: str,
    description: str,
) -> stripe.checkout.Session:
    """Amount is in the room's normal currency units (e.g. dollars), converted to cents here."""
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": description},
                    "unit_amount": int(round(amount * 100)),
                },
                "quantity": 1,
            }
        ],
        success_url=f"{settings.STRIPE_SUCCESS_URL}?booking_id={booking_id}",
        cancel_url=f"{settings.STRIPE_CANCEL_URL}?booking_id={booking_id}",
        expires_at=int(time.time()) + 1800,  # 30 minutes; Stripe min allowed is 30 min
        metadata={"booking_id": booking_id},
    )
    return session


def construct_webhook_event(payload: bytes, sig_header: str):
    """Raises stripe.error.SignatureVerificationError if invalid."""
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
