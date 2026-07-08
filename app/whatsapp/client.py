import httpx

from app.config import settings

GRAPH_API_VERSION = "v20.0"


def _base_url() -> str:
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.META_PHONE_NUMBER_ID}/messages"


async def send_text_message(to: str, body: str) -> dict:
    """Send a plain text WhatsApp message. `to` is the guest's wa_id (phone number, no +)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }
    return await _post(payload)


async def send_payment_link(to: str, checkout_url: str, amount: float, currency: str) -> dict:
    body = (
        f"Your booking is almost confirmed! 🎉\n\n"
        f"Amount due: {amount:.2f} {currency.upper()}\n\n"
        f"Please complete payment to confirm your reservation:\n{checkout_url}\n\n"
        f"This link will expire in 30 minutes."
    )
    return await send_text_message(to, body)


async def _post(payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_base_url(), json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
