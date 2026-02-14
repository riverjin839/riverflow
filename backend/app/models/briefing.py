from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class MarketBriefing(Base):
    __tablename__ = "market_briefing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    briefing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
