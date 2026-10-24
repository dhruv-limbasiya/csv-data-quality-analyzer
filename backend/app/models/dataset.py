from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # File details
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(512), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    
    # Dataset statistics
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    columns_metadata = Column(JSON, nullable=True)  # List of {name: str, type: str, sample_values: list}

    # Lineage / immutability tracking
    is_cleaned_version = Column(Boolean, default=False, nullable=False)
    original_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    owner = relationship("User", back_populates="datasets")
    analyses = relationship("Analysis", back_populates="dataset", cascade="all, delete-orphan")
    
    # Self-referential relationship for cleaned datasets derived from this original
    cleaned_versions = relationship(
        "Dataset",
        backref="original_dataset",
        remote_side=[id],
        foreign_keys=[original_dataset_id]
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, name='{self.original_filename}', rows={self.row_count}, cols={self.column_count})>"
