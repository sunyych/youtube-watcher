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
    llm_model: str = "qwen2.5:8b"
    
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
    
    # JWT
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 365  # 1 year
    
    @property
    def database_url(self) -> str:
        """Get database connection URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
