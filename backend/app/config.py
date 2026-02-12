"""Configuration management"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Web Configuration
    web_password: str = "admin123"
    web_port: int = 8080
    api_port: int = 8000
    
    # LLM Configuration
    ollama_url: str = "http://host.docker.internal:11434"
    vllm_url: Optional[str] = None
    llm_model: str = "qwen3"
    
    # Audio pipeline (queue: extract → resample → denoise → VAD → slice → Whisper → Qwen3)
    audio_target_sample_rate: int = 16000
    audio_enable_denoise: bool = False
    audio_denoise_backend: str = "noisereduce"
    vad_threshold: float = 0.5
    vad_min_silence_duration_ms: int = 2000
    vad_speech_pad_ms: int = 400
    vad_max_speech_duration_s: float = 30.0
    
    # Hardware Acceleration
    acceleration: str = "cpu"  # mlx, cuda, cpu
    
    # Database
    postgres_user: str = "youtube_watcher"
    postgres_password: str = "youtube_watcher_pass"
    postgres_db: str = "youtube_watcher_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    
    # Data Directories
    video_storage_dir: str = "./data/videos"
    postgres_data_dir: str = "./data/postgres"

    # yt-dlp / YouTube download
    # Extra retry wrapper around yt-dlp extraction (in addition to yt-dlp's internal retries)
    ytdlp_download_max_attempts: int = 3
    ytdlp_download_retry_backoff_seconds: float = 2.0

    # Queue worker guardrails: pause downloads if "blocked" happens too often
    # When N videos fail with "sign in / not a bot" etc., pause scheduling new downloads.
    queue_blocked_threshold: int = 3
    # Pause duration in seconds. Set 0 to effectively pause "forever" (until restart).
    queue_blocked_pause_seconds: int = 3600
    
    # JWT
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 365  # 1 year

    # Auth
    # When false, /api/auth/register will be disabled (useful for closing registration).
    allow_registration: bool = True
    
    @property
    def database_url(self) -> str:
        """Get database connection URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
