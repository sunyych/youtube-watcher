"""
Transcribe runner: HTTP API for GPU-accelerated transcription.
POST /transcribe -> 202 + job_id; GET /transcribe/{job_id} -> pending/completed/failed.
Supports multiple concurrent jobs (default 3), one per GPU (cuda:0, cuda:1, cuda:2).
"""
import logging
import os
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import (
    PORT,
    WHISPER_MODEL_SIZE,
    MAX_CONCURRENT_JOBS,
    NUM_GPUS,
    WHISPER_RELEASE_GPU_WHEN_IDLE,
)
from pipeline import run_pipeline
from whisper_service import WhisperService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Transcribe Runner", version="1.0")

# job_id -> {"status": "pending"|"processing"|"completed"|"failed", "progress": 0.0~1.0, "result": {...}, "error": "..."}
jobs: dict = {}
_jobs_lock = threading.Lock()

# One WhisperService per GPU (lazy init in worker threads)
_whisper_services: dict[int, WhisperService] = {}
_whisper_lock = threading.Lock()
# GPUs that have been marked unhealthy (e.g. repeated CUDA invalid argument). We stop scheduling new jobs to them.
_disabled_devices: set[int] = set()
# Active job count per device_id, used to know when a GPU becomes idle so we can optionally release its model.
_active_jobs_per_device: dict[int, int] = {}
# Round-robin device assignment for incoming jobs (skips disabled devices)
_device_counter = 0
_device_counter_lock = threading.Lock()

# Bounded pool: at most MAX_CONCURRENT_JOBS run at once (e.g. 3 GPUs)
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)
logger.info("Transcribe runner: max_concurrent_jobs=%s, num_gpus=%s", MAX_CONCURRENT_JOBS, NUM_GPUS)

# In-memory job queue: acceptor enqueues, dispatcher thread assigns jobs to GPUs.
_job_queue: Queue = Queue()
_dispatcher_thread = threading.Thread(target=lambda: _dispatcher_loop(), daemon=True)
_dispatcher_thread.start()


def _get_whisper(device_id: int) -> WhisperService:
    global _whisper_services
    with _whisper_lock:
        if device_id in _disabled_devices:
            raise RuntimeError(f"GPU device {device_id} is disabled due to previous CUDA errors")
        if device_id not in _whisper_services:
            device_str = f"cuda:{device_id}" if device_id < NUM_GPUS else "cuda:0"
            _whisper_services[device_id] = WhisperService(
                model_size=WHISPER_MODEL_SIZE,
                device=device_str,
            )
        svc = _whisper_services[device_id]
        # If underlying service has marked itself unhealthy, disable this device and fail fast
        if hasattr(svc, "is_healthy") and not svc.is_healthy:
            logger.warning("WhisperService for device_id=%s is unhealthy, disabling this GPU", device_id)
            _disabled_devices.add(device_id)
            raise RuntimeError(f"GPU device {device_id} is disabled (unhealthy WhisperService)")
        return svc


def _pick_device_id() -> int:
    """
    Pick the next healthy GPU id in a round-robin fashion.
    Raises RuntimeError if no healthy GPUs are available.
    """
    with _device_counter_lock, _whisper_lock:
        global _device_counter
        if len(_disabled_devices) >= NUM_GPUS:
            raise RuntimeError("No healthy GPUs available")
        # Try at most NUM_GPUS times to find a non-disabled device
        for _ in range(NUM_GPUS):
            candidate = _device_counter % NUM_GPUS
            _device_counter += 1
            if candidate not in _disabled_devices:
                return candidate
        raise RuntimeError("No healthy GPUs available after round-robin scan")


def _release_whisper_if_idle(device_id: int) -> None:
    """
    If WHISPER_RELEASE_GPU_WHEN_IDLE is enabled, drop the WhisperService for
    this device so VRAM can be reclaimed. Caller must only invoke when the
    device has no active jobs (avoids re-acquiring _device_counter_lock and deadlock).
    """
    if not WHISPER_RELEASE_GPU_WHEN_IDLE:
        return
    with _whisper_lock:
        svc = _whisper_services.pop(device_id, None)
    if svc is not None:
        try:
            # Drop reference to underlying model and trigger GC so CTranslate2 can free VRAM
            if hasattr(svc, "model"):
                delattr(svc, "model")
        except Exception:
            # We don't want cleanup failures to break the worker
            logger.exception("Failed to release WhisperService model for device_id=%s", device_id)
        # Force garbage collection to help free GPU memory
        try:
            import gc

            gc.collect()
        except Exception:
            pass


def _release_device_after_job(device_id: int) -> None:
    """Decrement active job count for device and release GPU model if device is now idle."""
    is_idle = False
    with _device_counter_lock:
        if device_id in _active_jobs_per_device:
            _active_jobs_per_device[device_id] = max(0, _active_jobs_per_device[device_id] - 1)
            is_idle = _active_jobs_per_device[device_id] == 0
    if is_idle:
        _release_whisper_if_idle(device_id)


def _dispatcher_loop() -> None:
    """
    Background dispatcher: pulls jobs from the in-memory queue and schedules
    them onto available GPUs via the worker thread pool.
    """
    while True:
        job_id, audio_path, language = _job_queue.get()
        try:
            device_id = _pick_device_id()
        except RuntimeError as e:
            logger.exception("Failed to pick device for job %s: %s", job_id, e)
            with _jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = str(e)
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            continue
        _executor.submit(_run_job, job_id, audio_path, language, device_id)


def _run_job(job_id: str, audio_path: str, language: str | None, device_id: int):
    device_released = False
    try:
        # Track active jobs per device so we can know when a GPU becomes idle.
        with _device_counter_lock:
            _active_jobs_per_device[device_id] = _active_jobs_per_device.get(device_id, 0) + 1

        with _jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["progress"] = 0.0

        audio_chunks, chunk_metadata = run_pipeline(audio_path)
        if not audio_chunks or not chunk_metadata:
            with _jobs_lock:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 1.0
                jobs[job_id]["result"] = {
                    "text": "",
                    "language": language or "unknown",
                    "segments": [],
                }
            _release_device_after_job(device_id)
            device_released = True
            return

        def progress_cb(sec: float):
            # Approximate progress from segment end vs total duration (we don't have total here)
            with _jobs_lock:
                if job_id in jobs and jobs[job_id].get("status") == "processing":
                    p = jobs[job_id].get("progress", 0)
                    jobs[job_id]["progress"] = min(p + 0.05, 0.99)

        whisper = _get_whisper(device_id)
        result = whisper.transcribe_segments(
            audio_chunks,
            chunk_metadata,
            language=language,
            progress_callback=progress_cb,
            sample_rate=16000,
        )
        # Release GPU as soon as conversion is done (don't wait for finally).
        _release_device_after_job(device_id)
        device_released = True

        with _jobs_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 1.0
            jobs[job_id]["result"] = {
                "text": result.get("text", ""),
                "language": result.get("language", "unknown"),
                "segments": result.get("segments", []),
            }
    except Exception as e:
        logger.exception("Job %s failed: %s", job_id, e)
        with _jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
    finally:
        if not device_released:
            _release_device_after_job(device_id)

        try:
            os.unlink(audio_path)
        except OSError:
            pass


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    """
    Return a snapshot of all known transcription jobs.
    This is a lightweight overview endpoint; use /transcribe/{job_id} for full result text.
    """
    with _jobs_lock:
        job_items = list(jobs.items())
    overview = []
    for job_id, info in job_items:
        overview.append(
            {
                "job_id": job_id,
                "status": info.get("status"),
                "progress": info.get("progress", 0.0),
                "has_result": info.get("result") is not None,
                "error": info.get("error"),
            }
        )
    return {
        "total_jobs": len(overview),
        "jobs": overview,
    }


@app.post("/transcribe")
async def submit_transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(None),
):
    if not file.filename or not file.filename.lower().endswith((".wav", ".wave")):
        raise HTTPException(status_code=400, detail="Expected a WAV file")
    job_id = str(uuid.uuid4())
    suffix = Path(file.filename).suffix or ".wav"
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="transcribe_")
    try:
        content = await file.read()
        os.write(fd, content)
    finally:
        os.close(fd)
    with _jobs_lock:
        jobs[job_id] = {"status": "pending", "progress": 0.0, "result": None, "error": None}
    # Enqueue job; dispatcher thread will pick devices and schedule execution.
    _job_queue.put((job_id, path, language))
    return JSONResponse(status_code=202, content={"job_id": job_id})


@app.get("/transcribe/{job_id}")
async def get_transcribe_result(job_id: str):
    with _jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job["status"]
    if status == "pending" or status == "processing":
        return JSONResponse(
            status_code=202,
            content={
                "status": status,
                "progress": job.get("progress", 0.0),
            },
        )
    if status == "failed":
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "error": job.get("error", "Unknown error")},
        )
    # completed
    result = job.get("result") or {}
    return {
        "status": "completed",
        "text": result.get("text", ""),
        "language": result.get("language", "unknown"),
        "segments": result.get("segments", []),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
