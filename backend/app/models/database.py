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
    
    # Relationships
    video_records = relationship("VideoRecord", back_populates="user")
    playlists = relationship("Playlist", back_populates="user")


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
    upload_date = Column(DateTime(timezone=True), nullable=True)  # Video upload date from YouTube
    thumbnail_path = Column(String, nullable=True)  # Path to thumbnail image
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="video_records")


class Playlist(Base):
    """Playlist model"""
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False, default="默认播放列表")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="playlists")
    items = relationship("PlaylistItem", back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistItem.position")


class PlaylistItem(Base):
    """Playlist item model"""
    __tablename__ = "playlist_items"
    
    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False, index=True)
    video_record_id = Column(Integer, ForeignKey("video_records.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    playlist = relationship("Playlist", back_populates="items")
    video_record = relationship("VideoRecord")
