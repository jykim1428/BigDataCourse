from sqlalchemy import Column, Integer, String, Float, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func
from .db import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    product_url = Column(Text)
    rating = Column(Float)
    body = Column(Text)
    review_date = Column(String(32))              # 원문 날짜 문자열
    hash_id = Column(String(64), nullable=False)  # 중복 방지용 해시
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('hash_id', name='uq_review_hash'),
        Index('idx_reviews_source_id', 'source', 'id'),
        Index('idx_reviews_created_at', 'created_at'),
    )