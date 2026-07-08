from fastapi import FastAPI

from app.database import Base, engine, SessionLocal
from app.models import Room
from app.whatsapp.webhook import router as whatsapp_router
from app.payments.webhook import router as stripe_router
from app.rag.retriever import build_index, INDEX_PATH

import os

Base.metadata.create_all(bind=engine)

# Auto-seed on first boot if the DB has no rooms yet or the RAG index is missing.
# Safe to run on every deploy since both checks are idempotent no-ops once set up.
db = SessionLocal()
if db.query(Room).count() == 0:
    sample_rooms = [
        Room(room_number="101", room_type="Standard", price_per_night=80.0, max_guests=2),
        Room(room_number="201", room_type="Deluxe", price_per_night=140.0, max_guests=3),
        Room(room_number="301", room_type="Suite", price_per_night=250.0, max_guests=4),
    ]
    db.add_all(sample_rooms)
    db.commit()
db.close()

if not os.path.exists(INDEX_PATH):
    build_index()

app = FastAPI(title="Hotel WhatsApp Booking System")

app.include_router(whatsapp_router)
app.include_router(stripe_router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "hotel-whatsapp-booking"}