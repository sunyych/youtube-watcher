"""Tests for history"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from app.models.database import VideoRecord, VideoStatus


def test_get_history(authenticated_client: TestClient, db, test_user):
    """Test getting history"""
    # Create test records
    record1 = VideoRecord(
        user_id=test_user.id,
        url="https://www.youtube.com/watch?v=test1",
        title="Test Video 1",
        status=VideoStatus.COMPLETED,
        progress=100.0,
        summary="Test summary 1",
        transcript="Test transcript 1"
    )
    record2 = VideoRecord(
        user_id=test_user.id,
        url="https://www.youtube.com/watch?v=test2",
        title="Test Video 2",
        status=VideoStatus.COMPLETED,
        progress=100.0,
        summary="Test summary 2",
        transcript="Test transcript 2"
    )
    db.add(record1)
    db.add(record2)
    db.commit()
    
    response = authenticated_client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    assert any(item["id"] == record1.id for item in data)
    assert any(item["id"] == record2.id for item in data)


def test_get_history_detail(authenticated_client: TestClient, db, test_user):
    """Test getting history detail"""
    record = VideoRecord(
        user_id=test_user.id,
        url="https://www.youtube.com/watch?v=test",
        title="Test Video",
        status=VideoStatus.COMPLETED,
        progress=100.0,
        summary="Test summary",
        transcript="Test transcript"
    )
    db.add(record)
    db.commit()
    
    response = authenticated_client.get(f"/api/history/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == record.id
    assert data["title"] == "Test Video"
    assert data["summary"] == "Test summary"
    assert data["transcript"] == "Test transcript"


def test_export_markdown(authenticated_client: TestClient, db, test_user):
    """Test exporting markdown"""
    record = VideoRecord(
        user_id=test_user.id,
        url="https://www.youtube.com/watch?v=test",
        title="Test Video",
        status=VideoStatus.COMPLETED,
        progress=100.0,
        summary="Test summary",
        transcript="Test transcript",
        language="en"
    )
    db.add(record)
    db.commit()
    
    response = authenticated_client.get(f"/api/history/{record.id}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    content = response.text
    assert "Test Video" in content
    assert "Test summary" in content
    assert "Test transcript" in content
