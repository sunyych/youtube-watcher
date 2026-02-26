# Transcribe Runner

GPU-accelerated transcription service for the queue worker. Run this on a machine with an NVIDIA GPU; the main queue (on another host or the same host) sends WAV files here and polls for results.

## API

- **POST /transcribe** — Upload a WAV file (multipart `file`), optional form field `language`. Returns `202` with `{"job_id": "uuid"}`.
- **GET /transcribe/{job_id}** — Poll for result. Returns `202` with `{"status": "pending"|"processing", "progress": 0.0~1.0}` until done; then `200` with `{"status": "completed", "text", "language", "segments"}` or `{"status": "failed", "error": "..."}`.
- **GET /health** — Returns `200` when the service is up.

## Run on the GPU machine

### Using Docker Compose (recommended)

From this directory. The compose file builds **Dockerfile.gpu** (CUDA 12) and uses `WHISPER_DEVICE=cuda` by default:

```bash
cp ../.env.example .env   # optional: copy and set WHISPER_MODEL_SIZE, etc.
docker compose up -d --build
```

The service listens on port **8765**. Ensure the queue host can reach this host on that port (firewall, network). Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the host.

### Using Docker only (GPU)

```bash
docker build -f Dockerfile.gpu -t transcribe_runner .
docker run --gpus all -p 8765:8765 -e WHISPER_DEVICE=cuda transcribe_runner
```

### Environment variables

- `PORT` — Server port (default `8765`).
- `WHISPER_MODEL_SIZE` — Whisper model (default `medium`).
- `WHISPER_DEVICE` — `cuda` or `cpu`. Default is **`cuda`** when using Docker Compose / Dockerfile.gpu. Set to `cpu` if you run the GPU image without a GPU (e.g. fallback).
- `AUDIO_TARGET_SAMPLE_RATE`, `VAD_*` — Same as backend pipeline (optional; defaults match the main app).

## Connect the queue to the runner

On the host where the main app and queue run (e.g. in the repo root `.env`):

```bash
# Replace with the GPU machine's IP or hostname and the port (default 8765)
TRANSCRIBE_RUNNER_URL=http://<gpu-host>:8765
# Optional: max wait per job (default 7200 = 2 hours), poll interval (default 30s)
TRANSCRIBE_RUNNER_TIMEOUT_SECONDS=7200
TRANSCRIBE_RUNNER_POLL_INTERVAL_SECONDS=30
```

Then restart the queue service (e.g. `docker compose up -d queue`). If `TRANSCRIBE_RUNNER_URL` is empty, the queue uses local Whisper (slower, no GPU required).
