from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    keywords: Mapped[list | None] = mapped_column(ARRAY(Text))
    embedding = mapped_column(Vector(768), nullable=True)
    impact_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    theme: Mapped[str | None] = mapped_column(String(100))
    is_leading: Mapped[bool] = mapped_column(Boolean, default=False)
    crawled_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
