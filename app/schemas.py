from datetime import date
from typing import Optional

from pydantic import BaseModel


class BookingIntent(BaseModel):
    """Structured extraction target for the booking agent."""
    room_type: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    guests_count: Optional[int] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    ready_to_book: bool = False
    missing_fields: list[str] = []
