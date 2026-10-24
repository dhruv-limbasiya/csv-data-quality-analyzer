from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Scoring & Summaries
    overall_score = Column(Float, nullable=False)  # 0.0 to 100.0
    summary_stats = Column(JSON, nullable=False)  # Total missing, duplicates, outliers, etc.
    column_scores = Column(JSON, nullable=False)  # Quality score per column
    issues = Column(JSON, nullable=False)         # Detailed issues identified
    recommendations = Column(JSON, nullable=True) # Recommended cleaning actions

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    dataset = relationship("Dataset", back_populates="analyses")
    user = relationship("User", back_populates="analyses")

    def __repr__(self) -> str:
        return f"<Analysis(id={self.id}, dataset_id={self.dataset_id}, score={self.overall_score})>"
