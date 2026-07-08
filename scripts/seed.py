"""
Run once to set up sample data:
    python -m scripts.seed
"""
from app.database import Base, engine, SessionLocal
from app.models import Room
from app.rag.retriever import build_index

Base.metadata.create_all(bind=engine)

db = SessionLocal()

sample_rooms = [
    Room(room_number="101", room_type="Standard", price_per_night=80.0, max_guests=2),
    Room(room_number="201", room_type="Deluxe", price_per_night=140.0, max_guests=3),
    Room(room_number="301", room_type="Suite", price_per_night=250.0, max_guests=4),
]

for room in sample_rooms:
    exists = db.query(Room).filter(Room.room_number == room.room_number).first()
    if not exists:
        db.add(room)

db.commit()
db.close()

print("Seeded rooms.")

print("Building RAG index from data/*.txt ...")
build_index()
print("Done. You can now run: uvicorn app.main:app --reload")
