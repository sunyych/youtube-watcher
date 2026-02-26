"""Unit tests for queue worker processing.

These tests mock external services (yt-dlp, ffmpeg/whisper, LLM) and validate that
`process_video_task` updates DB state correctly.
"""

import pytest


@pytest.mark.asyncio
async def test_process_video_task_completes_with_mocked_services(db, test_user, tmp_path, monkeypatch):
    from app.models.database import VideoRecord, VideoStatus
    import app.queue_worker as queue_worker
    from tests.conftest import TestingSessionLocal

    # Use the same in-memory DB session factory as the app test client
    monkeypatch.setattr(queue_worker, "SessionLocal", TestingSessionLocal)

    # Write files into a temp dir instead of repo data/
    monkeypatch.setattr(queue_worker.settings, "video_storage_dir", str(tmp_path))

    video_id = "jNQXAC9IVRw"  # 11 chars
    url = f"https://www.youtube.com/watch?v={video_id}"

    record = VideoRecord(
        user_id=test_user.id,
        url=url,
        status=VideoStatus.PENDING,
        progress=0.0,
        language="en",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    class DummyDownloader:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def download(self, url: str, progress_callback=None):
            if progress_callback:
                progress_callback(100.0)
            # Create an empty placeholder video file
            video_path = tmp_path / f"{video_id}.mp4"
            video_path.write_bytes(b"")
            return {
                "id": video_id,
                "title": "Test Title",
                "duration": 1,
                "file_path": str(video_path),
                "thumbnail": None,
                "description": "",
                "upload_date": None,
            }

    class DummyAudioConverter:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def convert_to_audio(self, video_path: str):
            # No need to write the file for this unit test path
            return str(tmp_path / f"{video_id}.wav")

    class DummyThumbnailGenerator:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def generate_thumbnail(self, video_path: str, video_id_in: str):
            return None

    class DummyLLMService:
        async def format_transcript(self, text: str, language: str = "中文"):
            return text

        async def generate_summary(self, text: str, language: str = "中文"):
            return "unit-test-summary"

        async def generate_keywords(self, transcript: str, title: str, language: str = "中文"):
            return "k1,k2"

    # Patch service classes in queue_worker module
    monkeypatch.setattr(queue_worker, "VideoDownloader", DummyDownloader)
    monkeypatch.setattr(queue_worker, "AudioConverter", DummyAudioConverter)
    monkeypatch.setattr(queue_worker, "ThumbnailGenerator", DummyThumbnailGenerator)
    monkeypatch.setattr(queue_worker, "LLMService", DummyLLMService)
    monkeypatch.setattr(queue_worker, "get_whisper_service", lambda: None)  # force "transcription unavailable" path

    await queue_worker.process_video_task(record.id)

    # Verify via a fresh session (queue_worker opens its own sessions)
    check_db = TestingSessionLocal()
    try:
        updated = check_db.query(VideoRecord).filter(VideoRecord.id == record.id).first()
        assert updated is not None
        assert updated.status == VideoStatus.COMPLETED
        assert updated.progress == 100.0
        assert updated.title == "Test Title"
        assert updated.summary == "unit-test-summary"
        assert updated.keywords == "k1,k2"
        assert updated.transcript is not None
        assert updated.transcript.startswith("Transcription unavailable:")
        assert updated.transcript_file_path is not None
    finally:
        check_db.close()

    # Ensure transcript file was written
    transcript_path = tmp_path / f"{video_id}.txt"
    assert transcript_path.exists()
    assert transcript_path.read_text(encoding="utf-8").startswith("Transcription unavailable:")


@pytest.mark.asyncio
async def test_process_video_task_marks_failed_on_download_error(db, test_user, tmp_path, monkeypatch):
    from app.models.database import VideoRecord, VideoStatus
    import app.queue_worker as queue_worker
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(queue_worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(queue_worker.settings, "video_storage_dir", str(tmp_path))

    video_id = "jNQXAC9IVRw"
    url = f"https://www.youtube.com/watch?v={video_id}"

    record = VideoRecord(
        user_id=test_user.id,
        url=url,
        status=VideoStatus.PENDING,
        progress=0.0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    class FailingDownloader:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def download(self, url: str, progress_callback=None):
            raise Exception("boom-download")

    class DummyAudioConverter:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def convert_to_audio(self, video_path: str):
            return str(tmp_path / f"{video_id}.wav")

    class DummyThumbnailGenerator:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def generate_thumbnail(self, video_path: str, video_id_in: str):
            return None

    class DummyLLMService:
        async def generate_summary(self, text: str, language: str = "中文"):
            return "should-not-happen"

        async def generate_keywords(self, transcript: str, title: str, language: str = "中文"):
            return ""

    monkeypatch.setattr(queue_worker, "VideoDownloader", FailingDownloader)
    monkeypatch.setattr(queue_worker, "AudioConverter", DummyAudioConverter)
    monkeypatch.setattr(queue_worker, "ThumbnailGenerator", DummyThumbnailGenerator)
    monkeypatch.setattr(queue_worker, "LLMService", DummyLLMService)
    monkeypatch.setattr(queue_worker, "get_whisper_service", lambda: None)

    await queue_worker.process_video_task(record.id)

    check_db = TestingSessionLocal()
    try:
        updated = check_db.query(VideoRecord).filter(VideoRecord.id == record.id).first()
        assert updated is not None
        assert updated.status == VideoStatus.FAILED
        assert updated.error_message is not None
        assert "boom-download" in updated.error_message
    finally:
        check_db.close()


@pytest.mark.asyncio
async def test_process_video_task_full_pipeline_mock_success(db, test_user, tmp_path, monkeypatch):
    """Full pipeline mock: download → convert → pipeline (VAD+slice) → transcribe_segments → format_transcript → generate_summary."""
    import numpy as np
    from app.models.database import VideoRecord, VideoStatus
    import app.queue_worker as queue_worker
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(queue_worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(queue_worker.settings, "video_storage_dir", str(tmp_path))
    monkeypatch.setattr(queue_worker.settings, "transcribe_runner_url", "")  # use local Whisper path

    video_id = "jNQXAC9IVRw"
    url = f"https://www.youtube.com/watch?v={video_id}"

    record = VideoRecord(
        user_id=test_user.id,
        url=url,
        status=VideoStatus.PENDING,
        progress=0.0,
        language="en",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    call_order = []

    class DummyDownloader:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def download(self, url: str, progress_callback=None):
            call_order.append("download")
            if progress_callback:
                progress_callback(100.0)
            video_path = tmp_path / f"{video_id}.mp4"
            video_path.write_bytes(b"")
            return {
                "id": video_id,
                "title": "Test Title",
                "duration": 1,
                "file_path": str(video_path),
                "thumbnail": None,
                "description": "",
                "upload_date": None,
            }

    class DummyAudioConverter:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def convert_to_audio(self, video_path: str):
            call_order.append("convert_to_audio")
            return str(tmp_path / f"{video_id}.wav")

    class DummyThumbnailGenerator:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def generate_thumbnail(self, video_path: str, video_id_in: str):
            return None

    def dummy_run_pipeline(audio_path: str):
        call_order.append("run_pipeline")
        # Return one chunk so transcribe_segments is called
        chunk = np.zeros(16000, dtype=np.float32)
        meta = [{"offset": 0, "duration": 1.0, "segments": []}]
        return [chunk], meta

    class DummyWhisperService:
        def transcribe_segments(
            self,
            audio_chunks,
            chunk_metadata,
            language=None,
            progress_callback=None,
            sample_rate=16000,
        ):
            call_order.append("transcribe_segments")
            return {
                "text": "raw transcript from whisper",
                "language": "en",
                "language_probability": 0.9,
                "segments": [{"start": 0, "end": 1, "text": "raw transcript from whisper"}],
            }

    class DummyLLMService:
        async def format_transcript(self, text: str, language: str = "中文"):
            call_order.append("format_transcript")
            return f"formatted: {text}"

        async def generate_summary(self, text: str, language: str = "中文"):
            call_order.append("generate_summary")
            return "unit-test-summary"

        async def generate_keywords(self, transcript: str, title: str, language: str = "中文"):
            return "k1,k2"

    dummy_whisper = DummyWhisperService()
    monkeypatch.setattr(queue_worker, "VideoDownloader", DummyDownloader)
    monkeypatch.setattr(queue_worker, "AudioConverter", DummyAudioConverter)
    monkeypatch.setattr(queue_worker, "run_pipeline", dummy_run_pipeline)
    monkeypatch.setattr(queue_worker, "get_whisper_service", lambda: dummy_whisper)
    monkeypatch.setattr(queue_worker, "ThumbnailGenerator", DummyThumbnailGenerator)
    monkeypatch.setattr(queue_worker, "LLMService", DummyLLMService)

    await queue_worker.process_video_task(record.id)

    check_db = TestingSessionLocal()
    try:
        updated = check_db.query(VideoRecord).filter(VideoRecord.id == record.id).first()
        assert updated is not None
        assert updated.status == VideoStatus.COMPLETED
        assert updated.progress == 100.0
        assert updated.title == "Test Title"
        assert updated.summary == "unit-test-summary"
        assert updated.transcript is not None
        assert "formatted: raw transcript from whisper" == updated.transcript
        assert updated.transcript_file_path is not None
    finally:
        check_db.close()

    transcript_path = tmp_path / f"{video_id}.txt"
    assert transcript_path.exists()
    assert "formatted: raw transcript from whisper" in transcript_path.read_text(encoding="utf-8")

    # Call order: download → convert_to_audio → run_pipeline → transcribe_segments → format_transcript → generate_summary
    assert "download" in call_order
    assert "convert_to_audio" in call_order
    assert "run_pipeline" in call_order
    assert "transcribe_segments" in call_order
    assert "format_transcript" in call_order
    assert "generate_summary" in call_order
    assert call_order.index("run_pipeline") > call_order.index("convert_to_audio")
    assert call_order.index("transcribe_segments") > call_order.index("run_pipeline")
    assert call_order.index("format_transcript") > call_order.index("transcribe_segments")
    assert call_order.index("generate_summary") > call_order.index("format_transcript")


@pytest.mark.asyncio
async def test_process_video_task_uses_runner_when_configured_failure(db, test_user, tmp_path, monkeypatch):
    """When TRANSCRIBE_RUNNER_URL is set and runner returns failure, transcript is set to error message."""
    from app.models.database import VideoRecord, VideoStatus
    import app.queue_worker as queue_worker
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(queue_worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(queue_worker.settings, "video_storage_dir", str(tmp_path))
    monkeypatch.setattr(queue_worker.settings, "transcribe_runner_url", "http://runner:8765")

    video_id = "runnerFail"
    url = f"https://www.youtube.com/watch?v={video_id}"
    (tmp_path / f"{video_id}.wav").write_bytes(b"")  # so convert step has a file to point to

    record = VideoRecord(
        user_id=test_user.id,
        url=url,
        status=VideoStatus.PENDING,
        progress=0.0,
        language="en",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    class DummyDownloader:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def download(self, url: str, progress_callback=None):
            if progress_callback:
                progress_callback(100.0)
            (tmp_path / f"{video_id}.mp4").write_bytes(b"")
            return {
                "id": video_id,
                "title": "Test",
                "duration": 1,
                "file_path": str(tmp_path / f"{video_id}.mp4"),
                "thumbnail": None,
                "description": "",
                "upload_date": None,
            }

    class DummyAudioConverter:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def convert_to_audio(self, video_path: str):
            return str(tmp_path / f"{video_id}.wav")

    class DummyThumbnailGenerator:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def generate_thumbnail(self, video_path: str, video_id_in: str):
            return None

    class DummyLLMService:
        async def format_transcript(self, text: str, language: str = "中文"):
            return text

        async def generate_summary(self, text: str, language: str = "中文"):
            return "summary"

        async def generate_keywords(self, transcript: str, title: str, language: str = "中文"):
            return "k1,k2"

    async def mock_runner_none(audio_path, language, record_id, db, record):
        return None

    monkeypatch.setattr(queue_worker, "VideoDownloader", DummyDownloader)
    monkeypatch.setattr(queue_worker, "AudioConverter", DummyAudioConverter)
    monkeypatch.setattr(queue_worker, "ThumbnailGenerator", DummyThumbnailGenerator)
    monkeypatch.setattr(queue_worker, "LLMService", DummyLLMService)
    monkeypatch.setattr(queue_worker, "_transcribe_via_runner", mock_runner_none)

    await queue_worker.process_video_task(record.id)

    check_db = TestingSessionLocal()
    try:
        updated = check_db.query(VideoRecord).filter(VideoRecord.id == record.id).first()
        assert updated is not None
        assert updated.status == VideoStatus.COMPLETED
        assert "Transcription unavailable (runner failed" in (updated.transcript or "")
    finally:
        check_db.close()


@pytest.mark.asyncio
async def test_process_video_task_uses_runner_when_configured_success(db, test_user, tmp_path, monkeypatch):
    """When TRANSCRIBE_RUNNER_URL is set and runner returns result, transcript is formatted and saved."""
    from app.models.database import VideoRecord, VideoStatus
    import app.queue_worker as queue_worker
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(queue_worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(queue_worker.settings, "video_storage_dir", str(tmp_path))
    monkeypatch.setattr(queue_worker.settings, "transcribe_runner_url", "http://runner:8765")

    video_id = "runnerOk"
    url = f"https://www.youtube.com/watch?v={video_id}"
    (tmp_path / f"{video_id}.wav").write_bytes(b"")

    record = VideoRecord(
        user_id=test_user.id,
        url=url,
        status=VideoStatus.PENDING,
        progress=0.0,
        language="en",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    class DummyDownloader:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def download(self, url: str, progress_callback=None):
            if progress_callback:
                progress_callback(100.0)
            (tmp_path / f"{video_id}.mp4").write_bytes(b"")
            return {
                "id": video_id,
                "title": "Test",
                "duration": 1,
                "file_path": str(tmp_path / f"{video_id}.mp4"),
                "thumbnail": None,
                "description": "",
                "upload_date": None,
            }

    class DummyAudioConverter:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def convert_to_audio(self, video_path: str):
            return str(tmp_path / f"{video_id}.wav")

    class DummyThumbnailGenerator:
        def __init__(self, storage_dir: str):
            self.storage_dir = storage_dir

        def generate_thumbnail(self, video_path: str, video_id_in: str):
            return None

    class DummyLLMService:
        async def format_transcript(self, text: str, language: str = "中文"):
            return f"formatted: {text}"

        async def generate_summary(self, text: str, language: str = "中文"):
            return "summary"

        async def generate_keywords(self, transcript: str, title: str, language: str = "中文"):
            return "k1,k2"

    async def mock_runner_ok(audio_path, language, record_id, db, record):
        return {"text": "raw from runner", "language": "en", "segments": []}

    monkeypatch.setattr(queue_worker, "VideoDownloader", DummyDownloader)
    monkeypatch.setattr(queue_worker, "AudioConverter", DummyAudioConverter)
    monkeypatch.setattr(queue_worker, "ThumbnailGenerator", DummyThumbnailGenerator)
    monkeypatch.setattr(queue_worker, "LLMService", DummyLLMService)
    monkeypatch.setattr(queue_worker, "_transcribe_via_runner", mock_runner_ok)

    await queue_worker.process_video_task(record.id)

    check_db = TestingSessionLocal()
    try:
        updated = check_db.query(VideoRecord).filter(VideoRecord.id == record.id).first()
        assert updated is not None
        assert updated.status == VideoStatus.COMPLETED
        assert updated.transcript == "formatted: raw from runner"
        assert updated.language == "en"
    finally:
        check_db.close()

    assert (tmp_path / f"{video_id}.txt").exists()
    assert "formatted: raw from runner" in (tmp_path / f"{video_id}.txt").read_text(encoding="utf-8")

