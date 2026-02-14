from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class SearchCondition(Base):
    __tablename__ = "search_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_trade: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_trade_config: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    results: Mapped[list["SearchResult"]] = relationship(back_populates="condition")


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[int] = mapped_column(ForeignKey("search_conditions.id", ondelete="CASCADE"))
    ticker: Mapped[str | None] = mapped_column(String(10))
    ticker_name: Mapped[str | None] = mapped_column(String(50))
    matched_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    price_at_match: Mapped[float | None] = mapped_column(DECIMAL(12, 2))
    volume_at_match: Mapped[int | None] = mapped_column(BigInteger)
    match_details: Mapped[dict | None] = mapped_column(JSONB)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    traded: Mapped[bool] = mapped_column(Boolean, default=False)

    condition: Mapped["SearchCondition"] = relationship(back_populates="results")
