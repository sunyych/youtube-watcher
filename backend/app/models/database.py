"""Database models"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Enum as SQLEnum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()


class VideoStatus(str, enum.Enum):
    """Video processing status"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationship to video records
    video_records = relationship("VideoRecord", back_populates="user")


class VideoRecord(Base):
    """Video record model"""
    __tablename__ = "video_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Nullable for migration
    url = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    transcript_file_path = Column(String, nullable=True)  # Path to transcript file
    summary = Column(Text, nullable=True)
    language = Column(String, nullable=True)
    keywords = Column(Text, nullable=True)  # Comma-separated keywords for search
    status = Column(SQLEnum(VideoStatus), default=VideoStatus.PENDING, nullable=False)
    progress = Column(Float, default=0.0, nullable=False)  # 0-100
    queue_position = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship to user
    user = relationship("User", back_populates="video_records")
