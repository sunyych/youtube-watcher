"""Integration tests with a real test video"""
import pytest
from fastapi.testclient import TestClient
import time


# Use a short, public test video
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - first YouTube video, ~19 seconds


@pytest.mark.integration
def test_full_video_processing_flow(authenticated_client: TestClient, db):
    """Test full video processing flow with a real video"""
    # This test requires actual services to be running
    # It's marked as integration test and can be skipped in unit tests
    
    # Submit video for processing
    response = authenticated_client.post(
        "/api/video/process",
        json={"url": TEST_VIDEO_URL, "language": "en"}
    )
    
    assert response.status_code in [200, 201]
    data = response.json()
    record_id = data["id"]
    
    # Check initial status
    assert data["status"] in ["pending", "downloading"]
    assert data["progress"] >= 0
    
    # Poll for status updates (with timeout)
    max_wait = 300  # 5 minutes max
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status_response = authenticated_client.get(f"/api/video/status/{record_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        if status_data["status"] == "completed":
            # Verify completed record
            assert status_data["progress"] == 100.0
            assert status_data.get("title") is not None
            
            # Check history
            history_response = authenticated_client.get(f"/api/history/{record_id}")
            assert history_response.status_code == 200
            history_data = history_response.json()
            assert history_data.get("transcript") is not None
            assert history_data.get("summary") is not None
            
            # Test markdown export
            export_response = authenticated_client.get(f"/api/history/{record_id}/export")
            assert export_response.status_code == 200
            assert "text/markdown" in export_response.headers["content-type"]
            
            break
        elif status_data["status"] == "failed":
            pytest.fail(f"Video processing failed: {status_data.get('error_message')}")
        
        time.sleep(5)  # Wait 5 seconds between polls
    else:
        pytest.fail("Video processing timed out")
