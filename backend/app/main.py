"""FastAPI application main file"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import socket
import logging

from app.config import settings
from app.database import init_db
from app.routers import auth, video, history, playlist
from app.routers.video import get_whisper_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    
    # Initialize Whisper service (lazy initialization, just check availability)
    logger.info("Checking Whisper service availability...")
    whisper_svc = get_whisper_service()
    if whisper_svc:
        logger.info("Whisper service available")
    else:
        logger.warning("Whisper service not available (will be handled by queue worker)")
    
    # Print access information
    print_access_info()
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title="YouTube Watcher API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(video.router)
app.include_router(history.router)
app.include_router(playlist.router)


def print_access_info():
    """Print access information on startup"""
    try:
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "localhost"
    
    web_port = settings.web_port
    api_port = settings.api_port
    
    print("\n" + "="*60)
    print("YouTube Watcher 已启动!")
    print("="*60)
    print(f"\n本地访问:")
    print(f"  - 前端: http://localhost:{web_port}")
    print(f"  - API:  http://localhost:{api_port}")
    print(f"\n网络访问:")
    print(f"  - 前端: http://{local_ip}:{web_port}")
    print(f"  - API:  http://{local_ip}:{api_port}")
    print(f"\n配置信息:")
    print(f"  - LLM模型: {settings.llm_model}")
    print(f"  - Ollama地址: {settings.ollama_url}")
    print(f"  - 硬件加速: {settings.acceleration}")
    print("="*60 + "\n")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "YouTube Watcher API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}
