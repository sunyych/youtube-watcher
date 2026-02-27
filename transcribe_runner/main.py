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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import PORT, WHISPER_MODEL_SIZE, MAX_CONCURRENT_JOBS, NUM_GPUS
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
# Round-robin device assignment for incoming jobs
_device_counter = 0
_device_counter_lock = threading.Lock()

# Bounded pool: at most MAX_CONCURRENT_JOBS run at once (e.g. 3 GPUs)
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)
logger.info("Transcribe runner: max_concurrent_jobs=%s, num_gpus=%s", MAX_CONCURRENT_JOBS, NUM_GPUS)


def _get_whisper(device_id: int) -> WhisperService:
    global _whisper_services
    with _whisper_lock:
        if device_id not in _whisper_services:
            device_str = f"cuda:{device_id}" if device_id < NUM_GPUS else "cuda:0"
            _whisper_services[device_id] = WhisperService(
                model_size=WHISPER_MODEL_SIZE,
                device=device_str,
            )
        return _whisper_services[device_id]


def _run_job(job_id: str, audio_path: str, language: str | None, device_id: int):
    try:
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
        try:
            os.unlink(audio_path)
        except OSError:
            pass


@app.get("/health")
async def health():
    return {"status": "ok"}


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
    with _device_counter_lock:
        global _device_counter
        device_id = _device_counter % NUM_GPUS
        _device_counter += 1
    _executor.submit(_run_job, job_id, path, language, device_id)
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
            status_code=200,
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
