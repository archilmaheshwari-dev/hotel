import hashlib
import hmac

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Guest, Conversation, ProcessedEvent
from app.whatsapp.client import send_text_message
from app.conversation.handler import process_message

router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])


@router.get("")
def verify_webhook(request: Request):
    """Meta calls this once when you register the webhook URL."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not settings.META_APP_SECRET:
        return False
    expected = hmac.new(
        settings.META_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    received = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected, received)


@router.post("")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if settings.ENV != "development" and not _verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            # could be a status update (delivered/read) - ignore
            return {"status": "ignored"}

        message = messages[0]
        wa_id = message["from"]
        message_id = message["id"]
        text_body = message.get("text", {}).get("body", "")
    except (KeyError, IndexError):
        return {"status": "ignored"}

    # idempotency: Meta retries webhook delivery on timeout/non-200
    already_processed = (
        db.query(ProcessedEvent)
        .filter(ProcessedEvent.source == "whatsapp", ProcessedEvent.event_id == message_id)
        .first()
    )
    if already_processed:
        return {"status": "duplicate"}
    db.add(ProcessedEvent(source="whatsapp", event_id=message_id))
    db.commit()

    guest = db.query(Guest).filter(Guest.wa_id == wa_id).first()
    if not guest:
        guest = Guest(wa_id=wa_id)
        db.add(guest)
        db.commit()
        db.refresh(guest)

    conversation = db.query(Conversation).filter(Conversation.guest_id == guest.id).first()
    if not conversation:
        conversation = Conversation(guest_id=guest.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    reply_text, checkout_url = process_message(db, guest, conversation, text_body)

    await send_text_message(wa_id, reply_text)

    return {"status": "ok"}
