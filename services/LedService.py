from sqlalchemy import select
from sqlalchemy.orm import Session

from models.metrics import LedEvent


class LedService:
    def __init__(self, db: Session):
        self.db = db

    def read(self) -> bool:
        """Whether the LED strip should be on. Off until first told otherwise."""
        latest = self.db.scalar(select(LedEvent).order_by(LedEvent.id.desc()).limit(1))
        return latest.is_on if latest else False

    def write(self, is_on: bool) -> LedEvent:
        event = LedEvent(is_on=is_on)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def history(self, limit: int) -> list[LedEvent]:
        return list(self.db.scalars(select(LedEvent).order_by(LedEvent.id.desc()).limit(limit)))
