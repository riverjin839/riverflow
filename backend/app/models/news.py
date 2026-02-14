from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Integer, String, Text
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
    crawled_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
