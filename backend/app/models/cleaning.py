from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CleaningRecord(Base):
    __tablename__ = "cleaning_records"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Status: 'completed', 'failed'
    status = Column(String(50), nullable=False, default="completed")

    # Cleaning configuration applied (stored as JSON)
    cleaning_config = Column(JSON, nullable=False)

    # Detailed summary of cleaning operations, before/after metrics, warnings
    cleaning_summary = Column(JSON, nullable=False)

    # File storage references (private, server-controlled)
    output_filename = Column(String(255), nullable=True)
    output_file_path = Column(String(512), nullable=True)
    output_file_size_bytes = Column(BigInteger, nullable=True)

    # Dimensional metrics after cleaning
    output_row_count = Column(Integer, nullable=True)
    output_column_count = Column(Integer, nullable=True)

    # Optional error message if status is 'failed'
    error_message = Column(String(1000), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    dataset = relationship("Dataset", back_populates="cleaning_records")
    user = relationship("User", back_populates="cleaning_records")

    def __repr__(self) -> str:
        return f"<CleaningRecord(id={self.id}, dataset_id={self.dataset_id}, status='{self.status}')>"
