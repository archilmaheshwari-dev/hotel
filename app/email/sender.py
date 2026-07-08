import smtplib
from email.mime.text import MIMEText

from app.config import settings


def _send(subject: str, body: str, to: str | None = None) -> None:
    to_addr = to or settings.OWNER_EMAIL
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USERNAME
    msg["To"] = to_addr

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USERNAME, [to_addr], msg.as_string())


def send_booking_confirmed_email(
    guest_name: str,
    guest_phone: str,
    room_type: str,
    check_in: str,
    check_out: str,
    amount: float,
    currency: str,
) -> None:
    subject = f"✅ New confirmed booking — {room_type} ({check_in} to {check_out})"
    body = (
        f"A new booking has been paid and confirmed.\n\n"
        f"Guest: {guest_name}\n"
        f"WhatsApp: {guest_phone}\n"
        f"Room type: {room_type}\n"
        f"Check-in: {check_in}\n"
        f"Check-out: {check_out}\n"
        f"Amount paid: {amount:.2f} {currency.upper()}\n"
    )
    _send(subject, body)


def send_payment_failed_email(guest_phone: str, booking_id: str) -> None:
    subject = "⚠️ Payment not completed for a booking"
    body = f"Guest {guest_phone} did not complete payment for booking {booking_id}."
    _send(subject, body)
