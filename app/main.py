from fastapi import FastAPI

from app.database import Base, engine
from app.whatsapp.webhook import router as whatsapp_router
from app.payments.webhook import router as stripe_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hotel WhatsApp Booking System")

app.include_router(whatsapp_router)
app.include_router(stripe_router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "hotel-whatsapp-booking"}
