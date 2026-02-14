from datetime import datetime

from sqlalchemy import DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AutoTradeOrder(Base):
    __tablename__ = "auto_trade_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_conditions.id", ondelete="SET NULL")
    )
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_results.id", ondelete="SET NULL")
    )
    order_id: Mapped[str | None] = mapped_column(String(50))
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(DECIMAL(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted")
    broker: Mapped[str] = mapped_column(String(20), nullable=False, default="kis")
    strategy_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
