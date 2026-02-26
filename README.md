# YouTube Watcher

A Dockerized single-page application for downloading YouTube videos, converting to audio, transcribing with Whisper, and summarizing with LLM.

## Features

- 🎥 YouTube video download and audio conversion
- 🎤 Whisper speech transcription (multi-language, medium model)
- 🤖 LLM automatic summarization (Ollama/vLLM)
- 📝 Markdown note export
- 📊 Real-time queue and progress display
- 🔒 Password protection
- 🚀 Cross-platform support (Mac/Linux/Windows)
- ⚡ Hardware acceleration (MLX/CUDA/CPU)

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Ollama (optional, for local LLM)

### Installation

1. Clone the repository and navigate to the directory

2. Copy environment variables:
```bash
cp .env.example .env
```

3. Edit `.env` file to configure password and other settings

4. Start services:
```bash
docker compose up -d
```

**Note:** The backend code is automatically mounted for hot reload. Code changes in `backend/app/` will be automatically detected and reloaded without rebuilding the container.

5. Access the application:
   - Local: http://localhost:8080
   - Network: http://[your-ip]:8080

Access information will be displayed in the terminal on startup.

**Development Tips:**
- Backend code changes: Automatically reloaded (no rebuild needed)
- To rebuild after dependency changes: `docker compose build backend && docker compose up -d backend`
- To view logs: `docker compose logs -f backend`

## Configuration

Environment variables in `.env`:
- `WEB_PASSWORD`: Web access password
- `OLLAMA_URL`: Ollama service address (default: host.docker.internal:11434)
- `LLM_MODEL`: LLM model name (default: qwen2.5:8b)
- `ACCELERATION`: Hardware acceleration type (mlx/cuda/cpu)
- `TRANSCRIBE_RUNNER_URL`: Optional. If set, the queue sends audio to this GPU transcription service instead of running Whisper locally. See [transcribe_runner/README.md](transcribe_runner/README.md) for running the runner on an NVIDIA GPU machine.
- `ENABLE_REVERSE_PROXY`, `PROXY_DOMAIN`, `PROXY_HTTP_PORT`: Optional reverse proxy (see below)

### Public Network Access

**Option A: Direct access (no reverse proxy)**

1. **Configure API URL**: Set the `VITE_API_URL` environment variable in your frontend build or runtime:
   ```bash
   # In docker-compose.yml or .env
   VITE_API_URL=http://your-public-ip:8000
   ```

2. **Firewall**: Ensure ports 8080 (frontend) and 8000 (backend API) are open in your firewall.

3. **Access**: Access the application via `http://your-public-ip:8080`

**Option B: Reverse proxy (single entry, optional HTTPS)**

To expose the app via port 80/443 with optional automatic HTTPS, use the included Caddy reverse proxy. Configure in `.env` then start with the proxy profile:

1. **Enable the proxy**: Run with the `proxy` profile:
   ```bash
   docker compose --profile proxy up -d
   ```

2. **With a domain (HTTPS)**:
   - Set `PROXY_DOMAIN=your.domain.com` in `.env`.
   - Point DNS for that domain to your server.
   - Open firewall ports 80 and 443.
   - Access via `https://your.domain.com` (Caddy obtains and renews TLS certificates automatically).

3. **Without a domain (HTTP by IP)**:
   - Leave `PROXY_DOMAIN` empty in `.env`.
   - Open firewall port 80 (or set `PROXY_HTTP_PORT` to another port).
   - Access via `http://<server-ip>` (or `http://<server-ip>:PROXY_HTTP_PORT` if changed).

4. **Firewall**: For the reverse proxy, open port 80 and, if using a domain, port 443.

Without the proxy profile, behavior is unchanged: use `http://<IP>:8080` as before. For production you can omit the frontend port mapping and expose only the proxy (edit `docker-compose.yml` to remove the frontend `ports` section when using the proxy).

Note: The frontend automatically detects the API URL from the `VITE_API_URL` environment variable. If not set, it defaults to the same origin (useful for reverse proxy setups).

## Usage

1. Enter YouTube video URL on the main page
2. Select video language (for better Whisper accuracy)
3. Submit to add video to processing queue
4. View real-time processing progress
5. View summary and full transcript in history page after completion
6. Click "Export Markdown" to download notes

## Testing

### Backend Tests

```bash
# Run unit tests
cd backend
pytest tests/ -v -m "not integration"

# Run integration tests (requires services running)
pytest tests/ -v -m integration
```

### Frontend E2E Tests

```bash
# Install Playwright browsers (first time)
cd frontend
npx playwright install

# Run tests
npm run test:e2e

# Run tests with UI
npm run test:e2e:ui
```

## Test Video

Use this test video for testing:
- URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- Title: "Me at the zoo"
- Duration: ~19 seconds

## Project Structure

```
youtube-watcher/
├── frontend/          # React frontend
├── backend/           # FastAPI backend
├── data/             # Data directory (videos, database)
├── docker-compose.yml
└── .env.example
```

## Development

### Development Mode with Docker (Hot Reload)

The project now supports code mounting for hot reload, so you don't need to rebuild Docker images after code changes.

**Backend code changes are automatically reloaded:**
- Backend code is mounted from `./backend/app` to `/app/app` in the container
- Uvicorn runs with `--reload` flag, so Python code changes are automatically detected
- No need to rebuild or restart the container for backend code changes

**To use development mode:**

1. **Standard mode (with code mounting):**
   ```bash
   docker compose up -d
   ```
   Backend code is already mounted and will auto-reload on changes.

2. **Full development mode (optional, using override file):**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```

**Note:**
- Backend Python code changes: ✅ Auto-reload (no rebuild needed)
- Backend dependency changes (requirements.txt): ⚠️ Requires rebuild: `docker compose build backend`
- Frontend code changes: ⚠️ Requires rebuild: `docker compose build frontend` (or use local dev server)
- Queue worker code changes: ✅ Auto-reload (code is mounted)

**For frontend development, you can either:**
- Use local dev server (recommended for frontend):
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
- Or rebuild frontend after changes:
  ```bash
  docker compose build frontend
  docker compose up -d frontend
  ```

### Local Development (without Docker)

#### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Troubleshooting

### YouTube download fails (403/400 errors)

If you encounter YouTube download errors:
1. **Update yt-dlp**: The latest version is already included, but you can update manually:
   ```bash
   docker compose exec backend pip install --upgrade yt-dlp
   ```

2. **Try different video**: Some videos may have restrictions

### Docker build fails

If faster-whisper installation fails:
- Clean Docker cache: `docker system prune -a`
- Increase Docker disk space
- Ensure build tools are available

### Port conflicts

Modify ports in `.env`:
```
WEB_PORT=8081
API_PORT=8001
```

### Ollama connection fails

Ensure Ollama is running on the host and accessible via `host.docker.internal:11434`.

### Database connection fails

Check PostgreSQL container:

```bash
docker compose ps
docker compose logs postgres
```

### Reset Password

You can reset a user's password using the command-line tool:

**Using Docker:**

```bash
# Interactive mode (recommended)
docker compose exec backend python reset_password.py --interactive

# Command-line mode
docker compose exec backend python reset_password.py --username admin --new-password newpass123

# List all users
docker compose exec backend python reset_password.py --list-users
```

**Local development:**

```bash
cd backend

# Interactive mode (recommended)
python reset_password.py --interactive

# Command-line mode
python reset_password.py --username admin --new-password newpass123

# List all users
python reset_password.py --list-users
```

**Using API (requires authentication):**
You can also change your password through the API endpoint:

- `POST /api/auth/change-password`
- Requires: `old_password` and `new_password` in request body
- Requires: Bearer token authentication

### Change Username

You can change a user's username using the command-line tool:

**Using Docker:**

```bash
# Interactive mode (recommended)
docker compose exec backend python change_username.py --interactive

# Command-line mode (by old username)
docker compose exec backend python change_username.py --old-username admin --new-username newadmin

# Command-line mode (by user ID)
docker compose exec backend python change_username.py --user-id 1 --new-username newadmin

# List all users
docker compose exec backend python change_username.py --list-users
```

**Local development:**

```bash
cd backend

# Interactive mode (recommended)
python change_username.py --interactive

# Command-line mode (by old username)
python change_username.py --old-username admin --new-username newadmin

# Command-line mode (by user ID)
python change_username.py --user-id 1 --new-username newadmin

# List all users
python change_username.py --list-users
```

**Using API (requires authentication):**
You can also change your username through the API endpoint:

- `POST /api/auth/change-username`
- Requires: `new_username` in request body
- Requires: Bearer token authentication
- Note: Username must be at least 3 characters long and unique

## License

MIT
