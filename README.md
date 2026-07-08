<<<<<<< HEAD
# Hotel WhatsApp Booking System

WhatsApp-based hotel assistant: answers FAQs via RAG, takes bookings, verifies payment via
Stripe, and emails you when a booking is confirmed.

## Architecture

```
Guest (WhatsApp) → Meta Cloud API → /webhook/whatsapp → process_message()
                                                              ├─ classify: booking or faq
                                                              ├─ faq → RAG-retrieved answer
                                                              └─ booking → collect fields over
                                                                 multiple messages → create
                                                                 PENDING booking → Stripe link
                                                                      ↓
                                                          Guest pays → Stripe →
                                                          /webhook/stripe (signature verified)
                                                                      ↓
                                                    Booking → CONFIRMED, guest gets WhatsApp
                                                    confirmation, you get an email
```

No agent framework (LangGraph/LangChain) — just direct Groq SDK calls and plain Python
control flow. Conversation state (message history + partially-collected booking fields)
is stored as JSON on the `Conversation` row rather than in a graph checkpointer.

## 1. Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values (see below)
```

### Required accounts / keys
- **Meta for Developers app** with WhatsApp product added → gives you
  `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`, `META_APP_SECRET`.
  `META_WHATSAPP_VERIFY_TOKEN` is just a random string you invent and enter in both
  the Meta dashboard and your `.env`.
- **Stripe account** (test mode is fine to start) → `STRIPE_SECRET_KEY`. You'll get
  `STRIPE_WEBHOOK_SECRET` after registering the webhook (step 3 below).
- **Groq API key** (matches your existing hotel agent stack) → `GROQ_API_KEY`.
- **Gmail app password** (or any SMTP provider) → `SMTP_USERNAME` / `SMTP_PASSWORD`.

### Seed sample data + build RAG index
```bash
python -m scripts.seed
```
This creates 3 sample rooms (Standard/Deluxe/Suite) and builds a local RAG index
(`rag_index.pkl`) from `data/faq.txt` using sentence-transformers embeddings + numpy
cosine similarity — no Chroma, no C++ build tools required. Edit `data/faq.txt` with your
real hotel's policies, then re-run the seed script whenever you update it.

### Run locally
```bash
uvicorn app.main:app --reload
```

## 2. Expose locally for testing (before deploying)

Use `ngrok` (or Railway directly) so Meta/Stripe can reach your webhook:
```bash
ngrok http 8000
```
Use the `https://xxxx.ngrok.io` URL as your webhook base for steps 3-4 below.

## 3. Register the WhatsApp webhook

In Meta for Developers → your app → WhatsApp → Configuration:
- Callback URL: `https://<your-domain>/webhook/whatsapp`
- Verify token: same string as `META_WHATSAPP_VERIFY_TOKEN`
- Subscribe to the `messages` field

## 4. Register the Stripe webhook

Dashboard → Developers → Webhooks → Add endpoint:
- URL: `https://<your-domain>/webhook/stripe`
- Events: `checkout.session.completed`, `checkout.session.expired`,
  `checkout.session.async_payment_failed`
- Copy the signing secret into `STRIPE_WEBHOOK_SECRET`

For local testing, use the Stripe CLI instead: `stripe listen --forward-to localhost:8000/webhook/stripe`

## 5. Deploy (Railway, matching your existing stack)

- Push this repo to GitHub, connect it to a new Railway service
- Add a Postgres plugin, set `DATABASE_URL` to its connection string
- Set all other env vars from `.env` in Railway's variables tab
- Railway gives you a public URL — use that as `APP_BASE_URL` and re-register both
  webhooks (steps 3-4) pointing at it instead of ngrok

## Project structure

```
app/
  main.py                 FastAPI entrypoint, mounts both webhook routers
  config.py                Settings (env vars)
  database.py               SQLAlchemy engine/session
  models.py                  Room, Guest, Conversation, Booking, ProcessedEvent
  schemas.py                  BookingIntent (structured extraction target)
  whatsapp/
    client.py                  send_text_message, send_payment_link
    webhook.py                  GET (verify) + POST (receive) handlers
  payments/
    stripe_client.py             create_checkout_session, construct_webhook_event
    webhook.py                    Stripe webhook handler (signature-verified)
  email/
    sender.py                      SMTP notifications to you
  conversation/
    handler.py                       process_message(): classify → FAQ answer or booking
                                      field collection → Stripe session creation
  rag/
    retriever.py                       numpy + sentence-transformers index/retrieval
scripts/
  seed.py                                Sample rooms + builds RAG index
data/
  faq.txt                                 Edit this with your hotel's real FAQ content
```

## Key design decisions worth knowing

1. **Idempotency everywhere.** Both Meta and Stripe retry webhook deliveries on timeout.
   `ProcessedEvent` dedups by `message_id` / Stripe `event.id` before any side effect runs.
2. **Payment is the real approval gate**, not `interrupt_before` like your SQL agent uses.
   A booking sits in `PENDING` → `AWAITING_PAYMENT` and only flips to `CONFIRMED` once
   Stripe's webhook fires — never on the guest's say-so.
3. **Conversation state persists per WhatsApp number** as plain JSON on the `Conversation`
   row — `pending_booking_json` holds whatever fields have been collected so far, so a
   guest can drop off mid-booking (e.g. gave dates but not email) and resume later without
   re-entering everything.
4. **Stripe checkout links expire in 30 minutes** (Stripe's minimum). Expired/failed
   sessions auto-release the room hold via the `checkout.session.expired` webhook event.

## Next steps to harden for production

- Swap `checkout.session.completed` handling to also verify `payment_status == "paid"`
  (covers async payment methods) — currently assumes card payments only.
- Add a background job to auto-expire `PENDING` bookings that never got a Stripe session
  (e.g. crash between booking creation and session creation).
- Rate-limit per `wa_id` to avoid abuse driving up your Groq/Stripe usage.
- Add WhatsApp message templates for the confirmation message — free-form text only works
  within Meta's 24-hour customer service window.
=======
# hotel
>>>>>>> d110deabd164033dba895dcdcdf77a1a47ec4178
