# Transcribe Runner

GPU-accelerated transcription service for the queue worker. Run this on a machine with an NVIDIA GPU; the main queue (on another host or the same host) sends WAV files here and polls for results.

## API

- **POST /transcribe** — Upload a WAV file (multipart `file`), optional form field `language`. Returns `202` with `{"job_id": "uuid"}`.
- **GET /transcribe/{job_id}** — Poll for result. Returns `202` with `{"status": "pending"|"processing", "progress": 0.0~1.0}` until done; then `200` with `{"status": "completed", "text", "language", "segments"}` or `500` with `{"status": "failed", "error": "..."}`.
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
- `MAX_CONCURRENT_JOBS` — Max transcription jobs running at once, e.g. one per GPU (default `3`).
- `NUM_GPUS` — Number of GPUs; jobs are assigned round-robin to `cuda:0` … `cuda:(NUM_GPUS-1)` (default same as `MAX_CONCURRENT_JOBS`).
- `GPU_NAME_FILTER` — If set (e.g. `3060`), at startup the service runs `nvidia-smi`, keeps only GPUs whose name contains this string (case-insensitive), and sets `CUDA_VISIBLE_DEVICES` so only those are used. Use this to automatically use only your two RTX 3060s when you have other GPUs in the machine. Default in Docker Compose is **`3060`**.
- `CUDA_VISIBLE_DEVICES` — Alternative to `GPU_NAME_FILTER`: comma-separated GPU indices (e.g. `1,2`). All GPUs are passed in; this limits which ones the process sees. Ignored if `GPU_NAME_FILTER` is set and matches GPUs.
- `AUDIO_TARGET_SAMPLE_RATE`, `VAD_*` — Same as backend pipeline (optional; defaults match the main app).

## Connect the queue to the runner

On the host where the main app and queue run (e.g. in the repo root `.env`):

```bash
# Replace with the GPU machine's IP or hostname and the port (default 8765)
TRANSCRIBE_RUNNER_URL=http://<gpu-host>:8765
# Optional: max wait per job (default 7200 = 2 hours), poll interval (default 30s), concurrent jobs (default 3)
TRANSCRIBE_RUNNER_TIMEOUT_SECONDS=7200
TRANSCRIBE_RUNNER_POLL_INTERVAL_SECONDS=30
TRANSCRIBE_RUNNER_CONCURRENCY=3
```

**Three GPUs, three concurrent tasks:** To run three transcription tasks at once (one per GPU), set queue-side `TRANSCRIBE_RUNNER_CONCURRENCY=3` and on the runner use defaults `MAX_CONCURRENT_JOBS=3` and `NUM_GPUS=3`. The queue sends up to three jobs to the runner; the runner runs them in parallel on `cuda:0`, `cuda:1`, and `cuda:2`.

Then restart the queue service (e.g. `docker compose up -d queue`). If `TRANSCRIBE_RUNNER_URL` is empty, the queue uses local Whisper (slower, no GPU required).

## Optional: restart container when all GPUs are idle

If the runner can get into a state where all GPUs are stuck at low utilization (e.g. after CUDA errors), you can run a script on the **GPU host** that checks GPU utilization and restarts the container when all GPUs are below a threshold (e.g. 30%) for two consecutive checks.

### Windows (every 60 seconds)

Double‑click or run in cmd:

```cmd
scripts\restart_if_gpus_idle.bat
```

The script loops every 60 seconds: if **all** GPUs are below 30% for two checks in a row (60 s apart), it runs `docker restart transcribe_runner`. Edit the first lines in the `.bat` to change `CONTAINER_NAME`, `THRESHOLD` (30), or `INTERVAL` (60). Requires `nvidia-smi` (NVIDIA drivers) and `docker` on PATH.

### Linux

```bash
chmod +x scripts/restart_if_gpus_idle.sh
./scripts/restart_if_gpus_idle.sh transcribe_runner 30 60
```

**Cron** (e.g. every 3 minutes): `crontab -e`:

```cron
*/3 * * * * /path/to/youtube-watcher/transcribe_runner/scripts/restart_if_gpus_idle.sh transcribe_runner 30 60
```
