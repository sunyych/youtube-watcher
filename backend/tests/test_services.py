"""Tests for services"""
import pytest
from unittest.mock import patch, MagicMock
import tempfile
import os

from app.services.markdown_exporter import MarkdownExporter
from app.services.queue_manager import QueueManager
import asyncio


def test_markdown_exporter():
    """Test markdown export"""
    video_record = {
        "title": "Test Video",
        "url": "https://www.youtube.com/watch?v=test",
        "summary": "This is a test summary",
        "transcript": "This is a test transcript",
        "language": "en",
        "created_at": "2024-01-01T00:00:00"
    }
    
    markdown = MarkdownExporter.export(video_record)
    
    assert "# Test Video" in markdown
    assert "This is a test summary" in markdown
    assert "This is a test transcript" in markdown
    assert "https://www.youtube.com/watch?v=test" in markdown


@pytest.mark.asyncio
async def test_queue_manager():
    """Test queue manager"""
    queue_manager = QueueManager(max_concurrent=2)
    
    # Test adding task
    async def dummy_processor(task):
        await asyncio.sleep(0.1)
        task['completed'] = True
    
    task_id = await queue_manager.add_task(
        processor=dummy_processor,
        task_data={'test': 'data'}
    )
    
    assert task_id > 0
    
    # Test queue status
    status = queue_manager.get_queue_status()
    assert status['queue_size'] >= 0
    
    # Cleanup
    queue_manager.stop_workers()
