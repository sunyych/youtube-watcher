"""Database models"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Float, Enum as SQLEnum, ForeignKey
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
    # Preferred language for generated summaries (e.g. 中文, English). Default 中文.
    summary_language = Column(String, nullable=True, default="中文")
    
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
    thumbnail_url = Column(Text, nullable=True)  # Remote thumbnail URL (from provider)
    source_video_id = Column(String, nullable=True, index=True)  # e.g. YouTube video id
    channel_id = Column(String, nullable=True)
    channel_title = Column(String, nullable=True, index=True)  # Publisher / channel name
    uploader_id = Column(String, nullable=True)
    uploader = Column(String, nullable=True)
    view_count = Column(BigInteger, default=0, nullable=False)
    like_count = Column(BigInteger, default=0, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
    read_count = Column(Integer, default=0, nullable=False)  # How many times the detail was opened
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="video_records")

    def bump_read_count(self) -> int:
        """Increment read_count for this record (in-memory)."""
        self.read_count = int(self.read_count or 0) + 1
        return int(self.read_count or 0)


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
