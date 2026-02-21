from datetime import date, datetime

from sqlalchemy import ARRAY, DECIMAL, Date, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class TradeJournal(Base):
    __tablename__ = "trade_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    ticker_name: Mapped[str | None] = mapped_column(String(50))
    buy_price: Mapped[float | None] = mapped_column(DECIMAL(12, 2))
    sell_price: Mapped[float | None] = mapped_column(DECIMAL(12, 2))
    quantity: Mapped[int | None] = mapped_column(Integer)
    profit_rate: Mapped[float | None] = mapped_column(DECIMAL(6, 2))
    buy_reason: Mapped[str | None] = mapped_column(Text)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    ai_verdict: Mapped[str | None] = mapped_column(String(20))
    ai_score: Mapped[int | None] = mapped_column(SmallInteger)
    ai_evaluation: Mapped[dict | None] = mapped_column(JSONB)
    chart_image_path: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
