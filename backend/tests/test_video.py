"""Tests for video processing"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


def test_process_video_request(authenticated_client: TestClient):
    """Test video processing request"""
    # Use a short test video URL (a public domain test video)
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - first YouTube video
    
    response = authenticated_client.post(
        "/api/video/process",
        json={"url": test_url, "language": "en"}
    )
    
    # Should accept the request and create a record
    assert response.status_code in [200, 201]
    data = response.json()
    assert "id" in data
    assert data["url"] == test_url
    assert "status" in data


def test_get_video_status(authenticated_client: TestClient, db, test_user):
    """Test getting video status"""
    from app.models.database import VideoRecord, VideoStatus
    
    # Create a test record
    record = VideoRecord(
        url="https://www.youtube.com/watch?v=test",
        user_id=test_user.id,
        status=VideoStatus.PENDING,
        progress=0.0
    )
    db.add(record)
    db.commit()
    
    response = authenticated_client.get(f"/api/video/status/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == record.id
    assert data["status"] == "pending"


def test_get_queue_status(authenticated_client: TestClient):
    """Test getting queue status"""
    response = authenticated_client.get("/api/video/queue")
    assert response.status_code == 200
    data = response.json()
    assert "queue_size" in data
    assert "processing" in data
